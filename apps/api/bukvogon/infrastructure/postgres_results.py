from __future__ import annotations

import asyncio
from collections.abc import Callable
import json
from typing import Any

import asyncpg

from bukvogon.domain.anti_cheat import AntiCheatDecision, VerificationStatus
from bukvogon.domain.ranked import (
    MultiplayerEloEngine,
    RankedPlayer,
    RankedRatingApplication,
    RankedResult,
    check_competitive_result_eligibility,
)
from bukvogon.services.anti_cheat import MAX_AUDIT_TRACE_BYTES, VERIFIER_VERSION
from bukvogon.services.races import PersistedRaceResult


_CREATE_RESULTS_TABLE = '''
CREATE TABLE IF NOT EXISTS race_results (
    race_id TEXT NOT NULL,
    player_id TEXT NOT NULL,
    place SMALLINT NOT NULL CHECK (place > 0),
    cpm INTEGER NOT NULL CHECK (cpm >= 0),
    accuracy DOUBLE PRECISION NOT NULL CHECK (accuracy >= 0 AND accuracy <= 1),
    verification_status TEXT NOT NULL DEFAULT 'provisional',
    risk_score SMALLINT CHECK (risk_score >= 0 AND risk_score <= 100),
    risk_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    telemetry_coverage DOUBLE PRECISION CHECK (telemetry_coverage >= 0 AND telemetry_coverage <= 1),
    audit_trace BYTEA,
    verifier_version TEXT,
    verified_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (race_id, player_id)
)
'''

_CREATE_RANKED_RATINGS_TABLE = '''
CREATE TABLE IF NOT EXISTS ranked_player_ratings (
    player_id TEXT PRIMARY KEY,
    rating DOUBLE PRECISION NOT NULL DEFAULT 1000,
    games_played INTEGER NOT NULL DEFAULT 0 CHECK (games_played >= 0),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
'''

_CREATE_RATING_APPLICATIONS_TABLE = '''
CREATE TABLE IF NOT EXISTS ranked_race_rating_applications (
    race_id TEXT PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
'''

_MIGRATE_RESULTS_TABLE = '''
ALTER TABLE race_results
    ADD COLUMN IF NOT EXISTS verification_status TEXT NOT NULL DEFAULT 'provisional',
    ADD COLUMN IF NOT EXISTS risk_score SMALLINT,
    ADD COLUMN IF NOT EXISTS risk_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS telemetry_coverage DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS audit_trace BYTEA,
    ADD COLUMN IF NOT EXISTS verifier_version TEXT,
    ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ
'''

_UPSERT_RESULT = '''
INSERT INTO race_results (
    race_id, player_id, place, cpm, accuracy, verification_status, finished_at
)
VALUES ($1, $2, $3, $4, $5, $6, NOW())
ON CONFLICT (race_id, player_id) DO UPDATE SET
    place = EXCLUDED.place,
    cpm = EXCLUDED.cpm,
    accuracy = EXCLUDED.accuracy,
    finished_at = EXCLUDED.finished_at
'''

_UPDATE_VERIFICATION = '''
UPDATE race_results SET
    verification_status = $3,
    risk_score = $4,
    risk_reasons = $5::jsonb,
    telemetry_coverage = $6,
    audit_trace = $7,
    verifier_version = $8,
    verified_at = CASE WHEN $3 = 'verified' THEN COALESCE(verified_at, NOW()) ELSE verified_at END
WHERE race_id = $1 AND player_id = $2
'''

_FETCH_RANKED_RESULTS = '''
SELECT player_id, place, verification_status
FROM race_results
WHERE race_id = $1
ORDER BY place ASC, player_id ASC
'''

_CLAIM_RATING_APPLICATION = '''
INSERT INTO ranked_race_rating_applications (race_id, applied_at)
VALUES ($1, NOW())
ON CONFLICT (race_id) DO NOTHING
RETURNING race_id
'''

_ENSURE_PLAYER_RATING = '''
INSERT INTO ranked_player_ratings (player_id, rating, games_played, updated_at)
VALUES ($1, 1000, 0, NOW())
ON CONFLICT (player_id) DO NOTHING
'''

_FETCH_PLAYER_RATINGS = '''
SELECT player_id, rating, games_played
FROM ranked_player_ratings
WHERE player_id = ANY($1::text[])
ORDER BY player_id ASC
'''

_FETCH_PLAYER_RATINGS_FOR_UPDATE = '''
SELECT player_id, rating, games_played
FROM ranked_player_ratings
WHERE player_id = ANY($1::text[])
ORDER BY player_id ASC
FOR UPDATE
'''

_UPDATE_PLAYER_RATING = '''
UPDATE ranked_player_ratings
SET rating = $2,
    games_played = games_played + 1,
    updated_at = NOW()
WHERE player_id = $1
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
                await connection.execute(_CREATE_RANKED_RATINGS_TABLE)
                await connection.execute(_CREATE_RATING_APPLICATIONS_TABLE)
                await connection.execute(_MIGRATE_RESULTS_TABLE)
            self._schema_ready = True

    @staticmethod
    def _rows_to_ranked_results(rows) -> list[RankedResult]:
        return [
            RankedResult(
                user_id=str(row['player_id']),
                place=int(row['place']),
                verification_status=VerificationStatus(str(row['verification_status'])),
            )
            for row in rows
        ]

    @staticmethod
    def _ratings_from_rows(rows) -> dict[str, float]:
        return {str(row['player_id']): float(row['rating']) for row in rows}

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
                result.verification_status.value,
            )

    async def update_verification(
        self,
        race_id: str,
        player_id: str,
        decision: AntiCheatDecision,
        *,
        audit_trace: bytes | None = None,
    ) -> None:
        if audit_trace is not None and len(audit_trace) > MAX_AUDIT_TRACE_BYTES:
            raise ValueError('anti-cheat audit trace exceeds storage bound')

        pool = await self._get_pool()
        await self._ensure_schema(pool)
        reasons_json = json.dumps(list(decision.reasons), ensure_ascii=False, separators=(',', ':'))

        async with pool.acquire() as connection:
            await connection.execute(
                _UPDATE_VERIFICATION,
                race_id,
                player_id,
                decision.status.value,
                decision.risk_score,
                reasons_json,
                decision.telemetry_coverage,
                audit_trace,
                VERIFIER_VERSION,
            )

    async def fetch_ranked_results(self, race_id: str) -> list[RankedResult]:
        if not race_id:
            raise ValueError('race_id is required')

        pool = await self._get_pool()
        await self._ensure_schema(pool)
        async with pool.acquire() as connection:
            rows = await connection.fetch(_FETCH_RANKED_RESULTS, race_id)
        return self._rows_to_ranked_results(rows)

    async def apply_ranked_rating(self, race_id: str) -> RankedRatingApplication:
        if not race_id:
            raise ValueError('race_id is required')

        pool = await self._get_pool()
        await self._ensure_schema(pool)
        engine = MultiplayerEloEngine(k_factor=32.0)

        async with pool.acquire() as connection:
            async with connection.transaction():
                result_rows = await connection.fetch(_FETCH_RANKED_RESULTS, race_id)
                results = self._rows_to_ranked_results(result_rows)
                if len(results) < 2:
                    raise ValueError('ranked rating requires at least two race results')
                if any(
                    not check_competitive_result_eligibility(result.verification_status).counts_for_mmr
                    for result in results
                ):
                    raise ValueError('ranked rating requires verified results')

                player_ids = sorted(result.user_id for result in results)
                claimed = await connection.fetchrow(_CLAIM_RATING_APPLICATION, race_id)
                if claimed is None:
                    current_rows = await connection.fetch(_FETCH_PLAYER_RATINGS, player_ids)
                    current_ratings = self._ratings_from_rows(current_rows)
                    if set(current_ratings) != set(player_ids):
                        raise ValueError('ranked rating ledger is inconsistent')
                    return RankedRatingApplication(ratings=current_ratings, applied=False)

                for player_id in player_ids:
                    await connection.execute(_ENSURE_PLAYER_RATING, player_id)

                rating_rows = await connection.fetch(_FETCH_PLAYER_RATINGS_FOR_UPDATE, player_ids)
                current_ratings = self._ratings_from_rows(rating_rows)
                if set(current_ratings) != set(player_ids):
                    raise ValueError('failed to initialize ranked player ratings')

                players = [
                    RankedPlayer(user_id=player_id, rating=current_ratings[player_id])
                    for player_id in player_ids
                ]
                updated_ratings = engine.rate(players, results)
                for player_id in player_ids:
                    await connection.execute(
                        _UPDATE_PLAYER_RATING,
                        player_id,
                        updated_ratings[player_id],
                    )

                return RankedRatingApplication(ratings=updated_ratings, applied=True)

    async def close(self) -> None:
        if self._pool is None:
            return
        pool = self._pool
        self._pool = None
        self._schema_ready = False
        await pool.close()
