from __future__ import annotations

from contextlib import asynccontextmanager
import os

from fastapi import FastAPI
from redis.asyncio import Redis

from bukvogon.api.auth import auth_router
from bukvogon.api.race_routes import router as race_router
from bukvogon.api.routes import router as v1_router
from bukvogon.infrastructure.postgres_auth import PostgresAuthRepository
from bukvogon.infrastructure.postgres_results import PostgresRaceResultRepository
from bukvogon.infrastructure.redis_anti_cheat import RedisAntiCheatStore
from bukvogon.infrastructure.redis_races import RedisRaceBroker, RedisRaceStore
from bukvogon.infrastructure.redis_ws_tickets import RedisWsTicketStore
from bukvogon.services.anti_cheat import RankedAntiCheatService
from bukvogon.services.auth import AuthService
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
    auth_repository = PostgresAuthRepository(database_url)
    auth_service = AuthService(auth_repository)
    race_store = RedisRaceStore(redis_client)
    race_broker = RedisRaceBroker(redis_client)
    race_hub = RaceRealtimeHub(race_broker)
    race_service = RaceService(
        store=race_store,
        persist_result=result_repository.persist,
    )
    anti_cheat_store = RedisAntiCheatStore(redis_client)
    ranked_anti_cheat = RankedAntiCheatService(
        store=anti_cheat_store,
        result_repository=result_repository,
    )
    ws_ticket_store = RedisWsTicketStore(redis_client)

    app.state.redis_client = redis_client
    app.state.race_results = result_repository
    app.state.auth_repository = auth_repository
    app.state.auth_service = auth_service
    app.state.race_service = race_service
    app.state.race_hub = race_hub
    app.state.anti_cheat_store = anti_cheat_store
    app.state.ranked_anti_cheat = ranked_anti_cheat
    app.state.ws_ticket_store = ws_ticket_store

    try:
        yield
    finally:
        await race_hub.close()
        await auth_repository.close()
        await result_repository.close()
        await redis_client.aclose()


app = FastAPI(title='BukvoGon API', version='0.1.0', lifespan=lifespan)


@app.get('/health')
def health() -> dict[str, str]:
    return {'status': 'ok'}


app.include_router(v1_router, prefix='/v1')
app.include_router(auth_router, prefix='/v1')
app.include_router(race_router, prefix='/v1')
