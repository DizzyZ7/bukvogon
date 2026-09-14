from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import secrets

from redis.asyncio import Redis
from redis.exceptions import WatchError


@dataclass(frozen=True, slots=True)
class WsTicketGrant:
    ticket: str
    expires_in_seconds: int


class RedisWsTicketStore:
    def __init__(self, client: Redis, *, ttl_seconds: int = 30) -> None:
        if ttl_seconds <= 0:
            raise ValueError('ttl_seconds must be positive')
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def key_for(ticket: str) -> str:
        if not ticket:
            raise ValueError('ticket is required')
        digest = hashlib.sha256(ticket.encode('utf-8')).hexdigest()
        return f'bukvogon:ranked-ws-ticket:{digest}'

    @staticmethod
    def _decode(raw: str | bytes) -> dict[str, object]:
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('invalid websocket ticket state')
        return payload

    async def issue(self, user_id: str, race_id: str, challenge_id: str) -> WsTicketGrant:
        if not user_id or not race_id or not challenge_id:
            raise ValueError('user_id, race_id and challenge_id are required')

        payload = json.dumps(
            {
                'user_id': user_id,
                'race_id': race_id,
                'challenge_id': challenge_id,
            },
            ensure_ascii=False,
            separators=(',', ':'),
        )
        for _ in range(3):
            ticket = secrets.token_urlsafe(32)
            created = await self._client.set(
                self.key_for(ticket),
                payload,
                ex=self._ttl_seconds,
                nx=True,
            )
            if created:
                return WsTicketGrant(ticket=ticket, expires_in_seconds=self._ttl_seconds)
        raise RuntimeError('failed to allocate websocket ticket')

    async def consume(self, ticket: str, *, race_id: str, challenge_id: str) -> str:
        if not ticket or not race_id or not challenge_id:
            raise ValueError('ticket, race_id and challenge_id are required')

        key = self.key_for(ticket)
        while True:
            pipeline = self._client.pipeline(transaction=True)
            try:
                await pipeline.watch(key)
                raw = await pipeline.get(key)
                if raw is None:
                    raise ValueError('ticket expired or consumed')
                payload = self._decode(raw)

                if payload.get('race_id') != race_id or payload.get('challenge_id') != challenge_id:
                    raise ValueError('ticket binding mismatch')
                user_id = str(payload.get('user_id') or '')
                if not user_id:
                    raise ValueError('invalid websocket ticket state')

                pipeline.multi()
                pipeline.delete(key)
                result = await pipeline.execute()
                if not result or int(result[0]) != 1:
                    continue
                return user_id
            except WatchError:
                continue
            finally:
                await pipeline.reset()
