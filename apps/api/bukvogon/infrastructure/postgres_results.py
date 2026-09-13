from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import asyncpg

from bukvogon.services.races import PersistedRaceResult


_CREATE_RESULTS_TABLE = '''
CREATE TABLE IF NOT EXISTS race_results (
    race_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    place SMALLINT NOT NULL CHECK (place > 0),
    cpm INTEGER NOT NULL CHECK (cpm >= 0),
    accuracy DOUBLE PRECISION NOT NULL CHECK (accuracy >= 0 AND accuracy <= 1),
    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (race_id, player_id)
)
'''

_UPSERT_RESULT = '''
INSERT INTO race_results (race_id, player_id, place, cpm, accuracy, finished_at)
VALUES ($1, $2, $3, $4, $5, NOW())
ON CONFLICT (race_id, player_id) DO UPDATE SET
    place = EXCLUDED.place,
    cpm = EXCLUDED.cpm,
    accuracy = EXCLUDED.accuracy,
    finished_at = EXCLUDED.finished_at
'''


class PostgresRaceResultRepository:
    def __init__(
        self,
        database_url: str,
        *,
        pool_factory: Callable[..., Any] = asyncpg.create_pool,
    ) -> None:
        if not database_url:
            raise ValueError('database_url is required')
        self._database_url = database_url
        self._pool_factory = pool_factory
        self._pool: Any | None = None
        self._pool_lock = asyncio.Lock()
        self._schema_lock = asyncio.Lock()
        self._schema_ready = False

    async def _get_pool(self):
        if self._pool is not None:
            return self._pool

        async with self._pool_lock:
            if self._pool is None:
                self._pool = await self._pool_factory(
                    dsn=self._database_url,
                    min_size=1,
                    max_size=5,
                    command_timeout=5,
                )
        return self._pool

    async def _ensure_schema(self, pool) -> None:
        if self._schema_ready:
            return

        async with self._schema_lock:
            if self._schema_ready:
                return
            async with pool.acquire() as connection:
                await connection.execute(_CREATE_RESULTS_TABLE)
            self._schema_ready = True

    async def persist(self, result: PersistedRaceResult) -> None:
        pool = await self._get_pool()
        await self._ensure_schema(pool)

        async with pool.acquire() as connection:
            await connection.execute(
                _UPSERT_RESULT,
                result.race_id,
                result.player_id,
                result.place,
                result.cpm,
                result.accuracy,
            )

    async def close(self) -> None:
        if self._pool is None:
            return
        pool = self._pool
        self._pool = None
        self._schema_ready = False
        await pool.close()
