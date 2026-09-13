from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Protocol


class SnapshotBroker(Protocol):
    async def publish(self, race_id: str, snapshot: dict[str, object]) -> None: ...
    def listen(self, race_id: str) -> AsyncIterator[dict[str, object]]: ...


class JsonSocket(Protocol):
    async def send_json(self, payload: dict[str, object]) -> None: ...


class RaceRealtimeHub:
    def __init__(self, broker: SnapshotBroker) -> None:
        self._broker = broker
        self._clients: dict[str, set[JsonSocket]] = {}
        self._listeners: dict[str, asyncio.Task[None]] = {}
        self._lock = asyncio.Lock()
        self._closed = False

    async def add(self, race_id: str, socket: JsonSocket) -> None:
        if self._closed:
            raise RuntimeError('realtime hub is closed')

        async with self._lock:
            clients = self._clients.setdefault(race_id, set())
            clients.add(socket)
            listener = self._listeners.get(race_id)
            if listener is None or listener.done():
                self._listeners[race_id] = asyncio.create_task(
                    self._listen_race(race_id),
                    name=f'bukvogon-race-listener:{race_id}',
                )

    async def remove(self, race_id: str, socket: JsonSocket) -> None:
        task_to_cancel: asyncio.Task[None] | None = None
        async with self._lock:
            clients = self._clients.get(race_id)
            if clients is not None:
                clients.discard(socket)
                if not clients:
                    self._clients.pop(race_id, None)
                    task_to_cancel = self._listeners.pop(race_id, None)

        if task_to_cancel is not None:
            task_to_cancel.cancel()
            await asyncio.gather(task_to_cancel, return_exceptions=True)

    def local_client_count(self, race_id: str) -> int:
        return len(self._clients.get(race_id, ()))

    async def publish(self, race_id: str, snapshot: dict[str, object]) -> None:
        await self._broker.publish(race_id, snapshot)

    async def _listen_race(self, race_id: str) -> None:
        try:
            async for snapshot in self._broker.listen(race_id):
                await self._broadcast_local(race_id, snapshot)
        except asyncio.CancelledError:
            raise

    async def _broadcast_local(self, race_id: str, snapshot: dict[str, object]) -> None:
        async with self._lock:
            sockets = tuple(self._clients.get(race_id, ()))

        if not sockets:
            return

        results = await asyncio.gather(
            *(socket.send_json(snapshot) for socket in sockets),
            return_exceptions=True,
        )

        failed = [
            socket
            for socket, result in zip(sockets, results, strict=True)
            if isinstance(result, BaseException)
        ]
        for socket in failed:
            await self.remove(race_id, socket)

    async def close(self) -> None:
        self._closed = True
        async with self._lock:
            tasks = tuple(self._listeners.values())
            self._listeners.clear()
            self._clients.clear()

        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
