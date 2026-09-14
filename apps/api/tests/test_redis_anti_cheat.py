import asyncio

import fakeredis.aioredis
import pytest

from bukvogon.domain.anti_cheat import TelemetryEvent, TelemetryKind
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
        assert evidence.errors == 3
        assert evidence.corrections == 2
        await client.aclose()

    asyncio.run(scenario())
