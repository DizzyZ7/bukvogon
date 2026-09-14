from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

import asyncpg

from bukvogon.domain.auth import (
    AuthenticatedPrincipal,
    IssuedSession,
    generate_session_token,
    hash_session_token,
)
from bukvogon.domain.entitlements import Entitlement, EntitlementStatus


_CREATE_USERS_TABLE = '''
CREATE TABLE IF NOT EXISTS users (
    user_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
'''

_CREATE_ENTITLEMENTS_TABLE = '''
CREATE TABLE IF NOT EXISTS user_entitlements (
    user_id TEXT PRIMARY KEY REFERENCES users(user_id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'free',
    valid_until TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
)
'''

_CREATE_SESSIONS_TABLE = '''
CREATE TABLE IF NOT EXISTS auth_sessions (
    session_id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    token_hash BYTEA NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    revoked_at TIMESTAMPTZ
)
'''

_INSERT_USER = '''
INSERT INTO users (user_id, created_at)
VALUES ($1, $2)
'''

_INSERT_ENTITLEMENT = '''
INSERT INTO user_entitlements (user_id, status, valid_until, updated_at)
VALUES ($1, $2, NULL, NOW())
'''

_INSERT_SESSION = '''
INSERT INTO auth_sessions (session_id, user_id, token_hash, expires_at, created_at)
VALUES ($1, $2, $3, $4, $5)
'''

_RESOLVE_SESSION = '''
SELECT
    sessions.user_id,
    sessions.expires_at,
    sessions.revoked_at,
    entitlements.status,
    entitlements.valid_until
FROM auth_sessions AS sessions
JOIN user_entitlements AS entitlements ON entitlements.user_id = sessions.user_id
WHERE sessions.token_hash = $1
LIMIT 1
'''

_REVOKE_SESSION = '''
UPDATE auth_sessions
SET revoked_at = COALESCE(revoked_at, $2)
WHERE token_hash = $1
  AND revoked_at IS NULL
'''

_GET_ENTITLEMENT = '''
SELECT user_id, status, valid_until
FROM user_entitlements
WHERE user_id = $1
'''

_GET_ENTITLEMENTS = '''
SELECT user_id, status, valid_until
FROM user_entitlements
WHERE user_id = ANY($1::text[])
ORDER BY user_id ASC
'''


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class PostgresAuthRepository:
    def __init__(
        self,
        database_url: str,
        *,
        pool_factory: Callable[..., Any] = asyncpg.create_pool,
        clock: Callable[[], datetime] | None = None,
        token_factory: Callable[[], str] = generate_session_token,
        id_factory: Callable[[], str] | None = None,
        session_ttl: timedelta = timedelta(days=30),
    ) -> None:
        if not database_url:
            raise ValueError('database_url is required')
        if session_ttl.total_seconds() <= 0:
            raise ValueError('session_ttl must be positive')

        self._database_url = database_url
        self._pool_factory = pool_factory
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._token_factory = token_factory
        self._id_factory = id_factory or (lambda: uuid4().hex)
        self._session_ttl = session_ttl
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
                await connection.execute(_CREATE_USERS_TABLE)
                await connection.execute(_CREATE_ENTITLEMENTS_TABLE)
                await connection.execute(_CREATE_SESSIONS_TABLE)
            self._schema_ready = True

    @staticmethod
    def _entitlement_from_row(row) -> Entitlement:
        return Entitlement(
            status=EntitlementStatus(str(row['status'])),
            valid_until=row['valid_until'],
        )

    async def create_guest_session(self) -> IssuedSession:
        pool = await self._get_pool()
        await self._ensure_schema(pool)

        now = _utc(self._clock())
        expires_at = now + self._session_ttl
        user_id = self._id_factory()
        session_id = self._id_factory()
        access_token = self._token_factory()
        token_hash = hash_session_token(access_token)

        async with pool.acquire() as connection:
            async with connection.transaction():
                await connection.execute(_INSERT_USER, user_id, now)
                await connection.execute(
                    _INSERT_ENTITLEMENT,
                    user_id,
                    EntitlementStatus.FREE.value,
                )
                await connection.execute(
                    _INSERT_SESSION,
                    session_id,
                    user_id,
                    token_hash,
                    expires_at,
                    now,
                )

        return IssuedSession(
            user_id=user_id,
            access_token=access_token,
            expires_at_epoch=int(expires_at.timestamp()),
        )

    async def resolve_session(self, token_hash: bytes) -> AuthenticatedPrincipal | None:
        if not token_hash:
            return None

        pool = await self._get_pool()
        await self._ensure_schema(pool)
        async with pool.acquire() as connection:
            row = await connection.fetchrow(_RESOLVE_SESSION, token_hash)

        if row is None:
            return None

        now = _utc(self._clock())
        revoked_at = row['revoked_at']
        if revoked_at is not None:
            return None

        expires_at = row['expires_at']
        if expires_at is None or _utc(expires_at) <= now:
            return None

        return AuthenticatedPrincipal(
            user_id=str(row['user_id']),
            entitlement=self._entitlement_from_row(row),
        )

    async def revoke_session(self, token_hash: bytes) -> bool:
        if not token_hash:
            return False

        pool = await self._get_pool()
        await self._ensure_schema(pool)
        now = _utc(self._clock())
        async with pool.acquire() as connection:
            status = await connection.execute(_REVOKE_SESSION, token_hash, now)
        return str(status).strip().endswith(' 1')

    async def get_entitlement(self, user_id: str) -> Entitlement | None:
        if not user_id:
            return None

        pool = await self._get_pool()
        await self._ensure_schema(pool)
        async with pool.acquire() as connection:
            row = await connection.fetchrow(_GET_ENTITLEMENT, user_id)
        if row is None:
            return None
        return self._entitlement_from_row(row)

    async def get_entitlements(self, user_ids: list[str]) -> dict[str, Entitlement]:
        ids = list(dict.fromkeys(user_id for user_id in user_ids if user_id))
        if not ids:
            return {}

        pool = await self._get_pool()
        await self._ensure_schema(pool)
        async with pool.acquire() as connection:
            rows = await connection.fetch(_GET_ENTITLEMENTS, ids)
        return {
            str(row['user_id']): self._entitlement_from_row(row)
            for row in rows
        }

    async def close(self) -> None:
        if self._pool is None:
            return
        pool = self._pool
        self._pool = None
        self._schema_ready = False
        await pool.close()
