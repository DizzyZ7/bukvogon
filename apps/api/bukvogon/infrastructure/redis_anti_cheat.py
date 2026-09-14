from __future__ import annotations

from dataclasses import dataclass
import json
import secrets
from uuid import uuid4

from redis.asyncio import Redis
from redis.exceptions import WatchError

from bukvogon.domain.anti_cheat import TelemetryEvidence, TelemetryEvent, TelemetryKind
from bukvogon.domain.race_session import RACE_TTL_SECONDS

MAX_STORED_EVENTS = 512


@dataclass(frozen=True, slots=True)
class RankedChallenge:
    challenge_id: str
    nonce: str
    race_id: str
    player_id: str
    target_text: str


@dataclass(frozen=True, slots=True)
class AntiCheatState:
    challenge_id: str
    race_id: str
    player_id: str
    target_text: str
    last_seq: int
    finalized: bool


class RedisAntiCheatStore:
    def __init__(self, client: Redis, *, ttl_seconds: int = RACE_TTL_SECONDS) -> None:
        self._client = client
        self._ttl_seconds = ttl_seconds

    @staticmethod
    def key_for(challenge_id: str) -> str:
        return f'bukvogon:anticheat:{challenge_id}'

    @staticmethod
    def _event_to_dict(event: TelemetryEvent) -> dict[str, object]:
        return {
            'dt_ms': event.dt_ms,
            'kind': event.kind.value,
            'trusted': event.trusted,
            'delta': event.delta,
            'input_type': event.input_type,
        }

    @staticmethod
    def _event_from_dict(payload: dict[str, object]) -> TelemetryEvent:
        return TelemetryEvent(
            dt_ms=int(payload['dt_ms']),
            kind=TelemetryKind(str(payload['kind'])),
            trusted=bool(payload['trusted']),
            delta=int(payload['delta']),
            input_type=(None if payload.get('input_type') is None else str(payload['input_type'])),
        )

    @staticmethod
    def _decode(raw: str | bytes) -> dict[str, object]:
        if isinstance(raw, bytes):
            raw = raw.decode('utf-8')
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError('invalid anti-cheat state')
        return payload

    async def issue_challenge(self, race_id: str, player_id: str, *, target_text: str) -> RankedChallenge:
        if not race_id or not player_id:
            raise ValueError('race_id and player_id are required')
        if not target_text:
            raise ValueError('target_text is required')

        for _ in range(3):
            challenge = RankedChallenge(
                challenge_id=uuid4().hex,
                nonce=secrets.token_urlsafe(24),
                race_id=race_id,
                player_id=player_id,
                target_text=target_text,
            )
            state = {
                'challenge_id': challenge.challenge_id,
                'nonce': challenge.nonce,
                'race_id': race_id,
                'player_id': player_id,
                'target_text': target_text,
                'last_seq': 0,
                'finalized': False,
                'events': [],
                'accepted_characters': 0,
                'errors': 0,
                'corrections': 0,
                'focused_batches': 0,
                'visible_batches': 0,
                'batch_count': 0,
            }
            created = await self._client.set(
                self.key_for(challenge.challenge_id),
                json.dumps(state, ensure_ascii=False, separators=(',', ':')),
                ex=self._ttl_seconds,
                nx=True,
            )
            if created:
                return challenge
        raise RuntimeError('failed to allocate unique anti-cheat challenge')

    async def _load_payload(self, challenge_id: str) -> dict[str, object]:
        raw = await self._client.get(self.key_for(challenge_id))
        if raw is None:
            raise ValueError('challenge expired')
        return self._decode(raw)

    async def get_state(self, challenge_id: str) -> AntiCheatState:
        payload = await self._load_payload(challenge_id)
        return AntiCheatState(
            challenge_id=str(payload['challenge_id']),
            race_id=str(payload['race_id']),
            player_id=str(payload['player_id']),
            target_text=str(payload['target_text']),
            last_seq=int(payload.get('last_seq', 0)),
            finalized=bool(payload.get('finalized', False)),
        )

    async def validate_and_advance(
        self,
        challenge_id: str,
        *,
        race_id: str,
        player_id: str,
        nonce: str,
        batch_seq: int,
    ) -> AntiCheatState:
        key = self.key_for(challenge_id)
        while True:
            pipeline = self._client.pipeline(transaction=True)
            try:
                await pipeline.watch(key)
                raw = await pipeline.get(key)
                if raw is None:
                    raise ValueError('challenge expired')
                payload = self._decode(raw)

                if bool(payload.get('finalized', False)):
                    raise ValueError('challenge finalized')
                if payload.get('race_id') != race_id or payload.get('player_id') != player_id:
                    raise ValueError('challenge binding mismatch')
                if payload.get('nonce') != nonce:
                    raise ValueError('challenge nonce mismatch')

                last_seq = int(payload.get('last_seq', 0))
                if batch_seq != last_seq + 1:
                    raise ValueError('batch sequence mismatch')

                ttl = await pipeline.ttl(key)
                payload['last_seq'] = batch_seq
                pipeline.multi()
                pipeline.set(
                    key,
                    json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
                    ex=(ttl if isinstance(ttl, int) and ttl > 0 else self._ttl_seconds),
                )
                await pipeline.execute()
                return AntiCheatState(
                    challenge_id=str(payload['challenge_id']),
                    race_id=str(payload['race_id']),
                    player_id=str(payload['player_id']),
                    target_text=str(payload['target_text']),
                    last_seq=batch_seq,
                    finalized=False,
                )
            except WatchError:
                continue
            finally:
                await pipeline.reset()

    async def append_evidence(
        self,
        challenge_id: str,
        *,
        events: tuple[TelemetryEvent, ...],
        accepted_characters: int,
        errors: int,
        corrections: int,
        focused: bool,
        visible: bool,
    ) -> None:
        key = self.key_for(challenge_id)
        while True:
            pipeline = self._client.pipeline(transaction=True)
            try:
                await pipeline.watch(key)
                raw = await pipeline.get(key)
                if raw is None:
                    raise ValueError('challenge expired')
                payload = self._decode(raw)
                if bool(payload.get('finalized', False)):
                    raise ValueError('challenge finalized')

                stored_events = payload.get('events', [])
                if not isinstance(stored_events, list):
                    stored_events = []
                stored_events.extend(self._event_to_dict(event) for event in events)
                payload['events'] = stored_events[-MAX_STORED_EVENTS:]
                payload['accepted_characters'] = max(int(payload.get('accepted_characters', 0)), accepted_characters)
                payload['errors'] = max(int(payload.get('errors', 0)), errors)
                payload['corrections'] = max(int(payload.get('corrections', 0)), corrections)
                payload['batch_count'] = int(payload.get('batch_count', 0)) + 1
                payload['focused_batches'] = int(payload.get('focused_batches', 0)) + int(focused)
                payload['visible_batches'] = int(payload.get('visible_batches', 0)) + int(visible)

                ttl = await pipeline.ttl(key)
                pipeline.multi()
                pipeline.set(
                    key,
                    json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
                    ex=(ttl if isinstance(ttl, int) and ttl > 0 else self._ttl_seconds),
                )
                await pipeline.execute()
                return
            except WatchError:
                continue
            finally:
                await pipeline.reset()

    async def get_evidence(self, challenge_id: str) -> TelemetryEvidence:
        payload = await self._load_payload(challenge_id)
        raw_events = payload.get('events', [])
        events = tuple(
            self._event_from_dict(item)
            for item in raw_events
            if isinstance(item, dict)
        )
        return TelemetryEvidence(
            events=events,
            accepted_characters=int(payload.get('accepted_characters', 0)),
            errors=int(payload.get('errors', 0)),
            corrections=int(payload.get('corrections', 0)),
        )

    async def finalize(self, challenge_id: str) -> None:
        key = self.key_for(challenge_id)
        while True:
            pipeline = self._client.pipeline(transaction=True)
            try:
                await pipeline.watch(key)
                raw = await pipeline.get(key)
                if raw is None:
                    raise ValueError('challenge expired')
                payload = self._decode(raw)
                payload['finalized'] = True
                ttl = await pipeline.ttl(key)
                pipeline.multi()
                pipeline.set(
                    key,
                    json.dumps(payload, ensure_ascii=False, separators=(',', ':')),
                    ex=(ttl if isinstance(ttl, int) and ttl > 0 else self._ttl_seconds),
                )
                await pipeline.execute()
                return
            except WatchError:
                continue
            finally:
                await pipeline.reset()
