import asyncio

import fakeredis.aioredis
import pytest

from bukvogon.domain.anti_cheat import TelemetryEvent, TelemetryKind, VerificationStatus
from bukvogon.domain.race_protocol import RankedTelemetryBatch
from bukvogon.infrastructure.redis_anti_cheat import RedisAntiCheatStore
from bukvogon.services.anti_cheat import RankedAntiCheatService


class FakeVerificationRepository:
    def __init__(self):
        self.updates = []

    async def update_verification(self, race_id, player_id, decision, *, audit_trace=None):
        self.updates.append((race_id, player_id, decision, audit_trace))


def _batch(challenge, *, seq=1, start=0, fragment='кот', events=None):
    if events is None:
        events = (
            TelemetryEvent(dt_ms=100, kind=TelemetryKind.INSERT, trusted=True, delta=1),
            TelemetryEvent(dt_ms=90, kind=TelemetryKind.INSERT, trusted=True, delta=1),
            TelemetryEvent(dt_ms=110, kind=TelemetryKind.INSERT, trusted=True, delta=1),
        )
    return RankedTelemetryBatch(
        challenge_id=challenge.challenge_id,
        nonce=challenge.nonce,
        batch_seq=seq,
        offset=start + len(fragment),
        fragment_start=start,
        fragment=fragment,
        errors=0,
        corrections=0,
        focused=True,
        visible=True,
        events=events,
    )


def test_ranked_batch_advances_only_server_matching_text_and_computes_metrics():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        repository = FakeVerificationRepository()
        service = RankedAntiCheatService(store=store, result_repository=repository)
        challenge = await service.issue_challenge('race-1', 'player-1', target_text='котик')

        progress = await service.accept_batch('race-1', 'player-1', _batch(challenge))

        assert progress.offset == 3
        assert progress.cpm == 600
        assert progress.accuracy == 1.0
        evidence = await store.get_evidence(challenge.challenge_id)
        assert evidence.accepted_characters == 3
        assert len(evidence.events) == 3
        await client.aclose()

    asyncio.run(scenario())


def test_wrong_text_fragment_does_not_consume_sequence():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        service = RankedAntiCheatService(store=store, result_repository=FakeVerificationRepository())
        challenge = await service.issue_challenge('race-1', 'player-1', target_text='котик')

        with pytest.raises(ValueError, match='fragment does not match target text'):
            await service.accept_batch('race-1', 'player-1', _batch(challenge, fragment='код'))

        state = await store.get_state(challenge.challenge_id)
        assert state.last_seq == 0
        await client.aclose()

    asyncio.run(scenario())


def test_replayed_batch_is_rejected_by_shared_sequence_state():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        service = RankedAntiCheatService(store=store, result_repository=FakeVerificationRepository())
        challenge = await service.issue_challenge('race-1', 'player-1', target_text='котик')
        batch = _batch(challenge)

        await service.accept_batch('race-1', 'player-1', batch)
        with pytest.raises(ValueError, match='batch sequence mismatch'):
            await service.accept_batch('race-1', 'player-1', batch)
        await client.aclose()

    asyncio.run(scenario())


def test_paste_can_never_finish_as_verified():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        repository = FakeVerificationRepository()
        service = RankedAntiCheatService(store=store, result_repository=repository)
        challenge = await service.issue_challenge('race-1', 'player-1', target_text='кот')
        paste = _batch(
            challenge,
            events=(TelemetryEvent(dt_ms=5, kind=TelemetryKind.PASTE, trusted=True, delta=3),),
        )

        await service.accept_batch('race-1', 'player-1', paste)
        decision = await service.verify_finish(challenge.challenge_id)

        assert decision.status is VerificationStatus.INVALID
        assert 'paste_advanced_text' in decision.reasons
        await client.aclose()

    asyncio.run(scenario())
