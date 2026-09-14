from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import AsyncIterator

from redis.asyncio import Redis
from redis.exceptions import WatchError

from bukvogon.domain.race_session import RACE_TTL_SECONDS, RaceSession


class RedisMutationLock:
    def __init__(
        self,
        client: Redis,
        key: str,
        *,
        lease_seconds: float = 5.0,
        blocking_seconds: float = 2.0,
    ) -> None:
        self._client = client
        self._key = key
        self._lease_ms = int(lease_seconds * 1000)
        self._blocking_seconds = blocking_seconds
        self._token = secrets.token_hex(16)
        self._acquired = False

    async def __aenter__(self) -> 'RedisMutationLock':
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._blocking_seconds
        while True:
            acquired = await self._client.set(
                self._key,
                self._token,
                nx=True,
                px=self._lease_ms,
            )
            if acquired:
                self._acquired = True
                return self
            if loop.time() >= deadline:
                raise TimeoutError('timed out waiting for race mutation lock')
            await asyncio.sleep(0.025)

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.release()

    async def release(self) -> None:
        if not self._acquired:
            return
        while True:
            pipeline = self._client.pipeline(transaction=True)
            try:
                await pipeline.watch(self._key)
                current = await pipeline.get(self._key)
                if isinstance(current, bytes):
                    current = current.decode('utf-8')
                if current != self._token:
                    await pipeline.reset()
                    self._acquired = False
                    return
                pipeline.multi()
                pipeline.delete(self._key)
                await pipeline.execute()
                self._acquired = False
                return
            except WatchError:
                continue
            finally:
                await pipeline.reset()


class RedisRaceStore:
    def __init__(self, client: Redis, *, ttl_seconds: int = RACE_TTL_SECONDS) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def key_for(race_id: str) -> str:
        return f'bukvogon:race:{race_id}'

    @staticmethod
    def lock_key_for(race_id: str) -> str:
        return f'bukvogon:race:{race_id}:lock'

    async def create(self, race: RaceSession) -> None:
        created = await self._client.set(
            self.key_for(race.race_id),
            json.dumps(race.to_dict(), separators=(',', ':')),
            ex=self._ttl_seconds,
            nx=True,
        )
        if not created:
            raise ValueError('race already exists')

    async def get(self, race_id: str) -> RaceSession | None:
        payload = await self._client.get(self.key_for(race_id))
        if payload is None:
            return None
        if isinstance(payload, bytes):
            payload = payload.decode('utf-8')
        return RaceSession.from_dict(json.loads(payload))

    async def save(self, race: RaceSession) -> None:
        key = self.key_for(race.race_id)
        if not await self._client.exists(key):
            raise ValueError('race does not exist')
        await self._client.set(
            key,
            json.dumps(race.to_dict(), separators=(',', ':')),
            ex=self._ttl_seconds,
        )

    def lock(self, race_id: str) -> RedisMutationLock:
        return RedisMutationLock(self._client, self.lock_key_for(race_id))


class RedisRaceBroker:
    def __init__(self, client: Redis) -> None:
        self._client = client

    @staticmethod
    def channel_for(race_id: str) -> str:
        return f'bukvogon:race:{race_id}:snapshots'

    async def publish(self, race_id: str, snapshot: dict[str, object]) -> None:
        await self._client.publish(
            self.channel_for(race_id),
            json.dumps(snapshot, separators=(',', ':')),
        )

    async def listen(self, race_id: str) -> AsyncIterator[dict[str, object]]:
        pubsub = self._client.pubsub()
        channel = self.channel_for(race_id)
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message.get('type') != 'message':
                    continue
                data = message.get('data')
                if isinstance(data, bytes):
                    data = data.decode('utf-8')
                if not isinstance(data, str):
                    continue
                payload = json.loads(data)
                if isinstance(payload, dict):
                    yield payload
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.aclose()
