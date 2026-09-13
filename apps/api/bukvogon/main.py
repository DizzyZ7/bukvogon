from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from redis.asyncio import Redis

from bukvogon.api.race_routes import router as race_router
from bukvogon.api.routes import router as v1_router
from bukvogon.infrastructure.postgres_results import PostgresRaceResultRepository
from bukvogon.infrastructure.redis_races import RedisRaceBroker, RedisRaceStore
from bukvogon.services.races import RaceService
from bukvogon.services.realtime import RaceRealtimeHub


@asynccontextmanager
async def lifespan(app: FastAPI):
    redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql://bukvogon:local-only@localhost:5432/bukvogon',
    )

    redis_client = Redis.from_url(
        redis_url,
        decode_responses=True,
        socket_connect_timeout=2,
        socket_timeout=2,
        health_check_interval=30,
    )
    result_repository = PostgresRaceResultRepository(database_url)
    race_store = RedisRaceStore(redis_client)
    race_broker = RedisRaceBroker(redis_client)
    race_hub = RaceRealtimeHub(race_broker)
    race_service = RaceService(
        store=race_store,
        persist_result=result_repository.persist,
    )

    app.state.redis_client = redis_client
    app.state.race_results = result_repository
    app.state.race_service = race_service
    app.state.race_hub = race_hub

    try:
        yield
    finally:
        await race_hub.close()
        await result_repository.close()
        await redis_client.aclose()


app = FastAPI(title='BukvoGon API', version='0.1.0', lifespan=lifespan)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


app.include_router(v1_router, prefix='/v1')
app.include_router(race_router, prefix='/v1')
