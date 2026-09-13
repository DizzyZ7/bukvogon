from __future__ import annotations

import json
from collections.abc import AsyncIterator

from redis.asyncio import Redis

from bukvogon.domain.race_session import RACE_TTL_SECONDS, RaceSession


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

    def lock(self, race_id: str):
        return self._client.lock(
            self.lock_key_for(race_id),
            timeout=5,
            blocking_timeout=2,
        )


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
