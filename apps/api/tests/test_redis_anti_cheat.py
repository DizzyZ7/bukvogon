import asyncio

import fakeredis.aioredis
import pytest

from bukvogon.domain.anti_cheat import TelemetryEvent, TelemetryKind, VerificationStatus, evaluate_evidence
from bukvogon.infrastructure.redis_anti_cheat import MAX_STORED_EVENTS, RedisAntiCheatStore


def test_challenge_is_bound_to_race_player_nonce_and_has_ttl():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client, ttl_seconds=1200)

        challenge = await store.issue_challenge('race-1', 'player-1', target_text='кот')

        assert challenge.race_id == 'race-1'
        assert challenge.player_id == 'player-1'
        assert challenge.target_text == 'кот'
        assert await client.ttl(store.key_for(challenge.challenge_id)) > 0
        await store.validate_and_advance(
            challenge.challenge_id,
            race_id='race-1',
            player_id='player-1',
            nonce=challenge.nonce,
            batch_seq=1,
        )

        with pytest.raises(ValueError, match='challenge binding mismatch'):
            await store.validate_and_advance(
                challenge.challenge_id,
                race_id='race-2',
                player_id='player-1',
                nonce=challenge.nonce,
                batch_seq=2,
            )

        with pytest.raises(ValueError, match='challenge nonce mismatch'):
            await store.validate_and_advance(
                challenge.challenge_id,
                race_id='race-1',
                player_id='player-1',
                nonce='wrong',
                batch_seq=2,
            )
        await client.aclose()

    asyncio.run(scenario())


def test_sequence_must_advance_exactly_once_and_replay_is_rejected():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        challenge = await store.issue_challenge('race-1', 'player-1', target_text='кот')

        await store.validate_and_advance(challenge.challenge_id, race_id='race-1', player_id='player-1', nonce=challenge.nonce, batch_seq=1)

        with pytest.raises(ValueError, match='batch sequence mismatch'):
            await store.validate_and_advance(challenge.challenge_id, race_id='race-1', player_id='player-1', nonce=challenge.nonce, batch_seq=1)
        with pytest.raises(ValueError, match='batch sequence mismatch'):
            await store.validate_and_advance(challenge.challenge_id, race_id='race-1', player_id='player-1', nonce=challenge.nonce, batch_seq=3)

        state = await store.get_state(challenge.challenge_id)
        assert state.last_seq == 1
        await client.aclose()

    asyncio.run(scenario())


def test_missing_or_finalized_challenge_rejects_new_batches():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        challenge = await store.issue_challenge('race-1', 'player-1', target_text='кот')

        await store.finalize(challenge.challenge_id)
        with pytest.raises(ValueError, match='challenge finalized'):
            await store.validate_and_advance(challenge.challenge_id, race_id='race-1', player_id='player-1', nonce=challenge.nonce, batch_seq=1)

        await client.delete(store.key_for(challenge.challenge_id))
        with pytest.raises(ValueError, match='challenge expired'):
            await store.validate_and_advance(challenge.challenge_id, race_id='race-1', player_id='player-1', nonce=challenge.nonce, batch_seq=1)
        await client.aclose()

    asyncio.run(scenario())


def test_evidence_buffer_is_bounded_and_keeps_cumulative_counters():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        challenge = await store.issue_challenge('race-1', 'player-1', target_text='а' * 1000)
        events = tuple(
            TelemetryEvent(dt_ms=50 + (index % 7), kind=TelemetryKind.INSERT, trusted=True, delta=1)
            for index in range(MAX_STORED_EVENTS + 40)
        )

        await store.append_evidence(
            challenge.challenge_id,
            events=events,
            accepted_characters=MAX_STORED_EVENTS + 40,
            errors=3,
            corrections=2,
            focused=True,
            visible=True,
        )
        evidence = await store.get_evidence(challenge.challenge_id)

        assert len(evidence.events) == MAX_STORED_EVENTS
        assert evidence.accepted_characters == MAX_STORED_EVENTS + 40
        assert evidence.observed_characters == MAX_STORED_EVENTS + 40
        assert evidence.elapsed_ms == sum(event.dt_ms for event in events)
        assert evidence.errors == 3
        assert evidence.corrections == 2
        await client.aclose()

    asyncio.run(scenario())


def test_hard_violation_survives_event_buffer_trimming():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)
        challenge = await store.issue_challenge('race-long', 'player-1', target_text='а' * 700)
        first = (TelemetryEvent(dt_ms=5, kind=TelemetryKind.PASTE, trusted=True, delta=3),)
        later = tuple(
            TelemetryEvent(dt_ms=60 + (index % 9), kind=TelemetryKind.INSERT, trusted=True, delta=1)
            for index in range(MAX_STORED_EVENTS + 80)
        )

        await store.append_evidence(
            challenge.challenge_id,
            events=first,
            accepted_characters=3,
            errors=0,
            corrections=0,
            focused=True,
            visible=True,
        )
        await store.append_evidence(
            challenge.challenge_id,
            events=later,
            accepted_characters=3 + len(later),
            errors=0,
            corrections=0,
            focused=True,
            visible=True,
        )
        evidence = await store.get_evidence(challenge.challenge_id)
        decision = evaluate_evidence(evidence)

        assert len(evidence.events) == MAX_STORED_EVENTS
        assert 'paste_advanced_text' in evidence.hard_reasons
        assert decision.status is VerificationStatus.INVALID
        assert 'paste_advanced_text' in decision.reasons
        await client.aclose()

    asyncio.run(scenario())
