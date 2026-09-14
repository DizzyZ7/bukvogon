import asyncio

import fakeredis.aioredis
import pytest

from bukvogon.infrastructure.redis_anti_cheat import RedisAntiCheatStore


def test_same_race_player_reuses_single_active_challenge_and_binding_ttl():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client, ttl_seconds=1200)

        first = await store.issue_challenge('race-1', 'player-1', target_text='котик')
        second = await store.issue_challenge('race-1', 'player-1', target_text='котик')

        assert second == first
        assert await client.ttl(store.binding_key_for('race-1', 'player-1')) > 0

        state = await store.get_state(first.challenge_id)
        assert state.last_seq == 0
        await client.aclose()

    asyncio.run(scenario())


def test_active_binding_cannot_be_reissued_with_another_target():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)

        await store.issue_challenge('race-1', 'player-1', target_text='котик')

        with pytest.raises(ValueError, match='challenge target mismatch'):
            await store.issue_challenge('race-1', 'player-1', target_text='самолет')

        await client.aclose()

    asyncio.run(scenario())


def test_finalized_binding_cannot_spawn_a_second_challenge():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisAntiCheatStore(client)

        challenge = await store.issue_challenge('race-1', 'player-1', target_text='котик')
        await store.finalize(challenge.challenge_id)

        with pytest.raises(ValueError, match='challenge finalized'):
            await store.issue_challenge('race-1', 'player-1', target_text='котик')

        await client.aclose()

    asyncio.run(scenario())
