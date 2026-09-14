import asyncio

import fakeredis.aioredis
import pytest

from bukvogon.infrastructure.redis_ws_tickets import RedisWsTicketStore


def test_ws_ticket_has_short_ttl_and_redis_key_does_not_expose_raw_ticket():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisWsTicketStore(client, ttl_seconds=30)

        grant = await store.issue('user-1', 'race-1', 'challenge-1')
        key = store.key_for(grant.ticket)

        assert grant.ticket
        assert grant.expires_in_seconds == 30
        assert grant.ticket not in key
        ttl = await client.ttl(key)
        assert 0 < ttl <= 30
        await client.aclose()

    asyncio.run(scenario())


def test_wrong_binding_is_rejected_without_consuming_ticket():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisWsTicketStore(client)
        grant = await store.issue('user-1', 'race-1', 'challenge-1')

        with pytest.raises(ValueError, match='ticket binding mismatch'):
            await store.consume(grant.ticket, race_id='race-2', challenge_id='challenge-1')
        with pytest.raises(ValueError, match='ticket binding mismatch'):
            await store.consume(grant.ticket, race_id='race-1', challenge_id='challenge-2')

        assert await store.consume(
            grant.ticket,
            race_id='race-1',
            challenge_id='challenge-1',
        ) == 'user-1'
        await client.aclose()

    asyncio.run(scenario())


def test_ws_ticket_is_consumed_exactly_once():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisWsTicketStore(client)
        grant = await store.issue('user-1', 'race-1', 'challenge-1')

        first = await store.consume(
            grant.ticket,
            race_id='race-1',
            challenge_id='challenge-1',
        )
        assert first == 'user-1'

        with pytest.raises(ValueError, match='ticket expired or consumed'):
            await store.consume(
                grant.ticket,
                race_id='race-1',
                challenge_id='challenge-1',
            )
        await client.aclose()

    asyncio.run(scenario())


def test_expired_or_missing_ws_ticket_fails_closed():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisWsTicketStore(client)
        grant = await store.issue('user-1', 'race-1', 'challenge-1')
        await client.delete(store.key_for(grant.ticket))

        with pytest.raises(ValueError, match='ticket expired or consumed'):
            await store.consume(
                grant.ticket,
                race_id='race-1',
                challenge_id='challenge-1',
            )
        await client.aclose()

    asyncio.run(scenario())
