import asyncio

import fakeredis.aioredis

from bukvogon.domain.race_session import RACE_TTL_SECONDS, RaceSession
from bukvogon.infrastructure.redis_races import RedisRaceBroker, RedisRaceStore


def test_redis_store_round_trips_race_and_refreshes_ttl():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        store = RedisRaceStore(client, ttl_seconds=RACE_TTL_SECONDS)
        race = RaceSession.create('race-redis', text_length=100, player_ids=['a', 'b'])

        await store.create(race)
        loaded = await store.get('race-redis')

        assert loaded is not None
        assert loaded.race_id == 'race-redis'
        assert await client.ttl(store.key_for('race-redis')) > 0

        async with store.lock('race-redis'):
            loaded.apply_progress('a', offset=40, cpm=320, accuracy=0.96)
            await store.save(loaded)

        refreshed = await store.get('race-redis')
        assert refreshed is not None
        assert refreshed.players['a'].offset == 40

        await client.aclose()

    asyncio.run(scenario())


def test_redis_broker_publishes_snapshots_to_subscriber():
    async def scenario():
        client = fakeredis.aioredis.FakeRedis(decode_responses=True)
        broker = RedisRaceBroker(client)
        received = asyncio.Event()
        payloads = []

        async def listener():
            async for payload in broker.listen('race-1'):
                payloads.append(payload)
                received.set()
                break

        task = asyncio.create_task(listener())
        await asyncio.sleep(0)
        await broker.publish('race-1', {'race_id': 'race-1', 'status': 'running', 'racers': []})
        await asyncio.wait_for(received.wait(), timeout=1)
        await task

        assert payloads[0]['race_id'] == 'race-1'
        await client.aclose()

    asyncio.run(scenario())
