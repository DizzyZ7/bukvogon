import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from bukvogon.domain.auth import hash_session_token
from bukvogon.domain.entitlements import Entitlement, EntitlementStatus
from bukvogon.infrastructure.postgres_auth import PostgresAuthRepository


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class FakeAuthConnection:
    def __init__(self):
        self.queries = []
        self.session_row = None
        self.entitlement_rows = []
        self.update_result = 'UPDATE 1'

    def transaction(self):
        return FakeTransaction()

    async def execute(self, query, *args):
        self.queries.append((query, args))
        if 'UPDATE auth_sessions' in query:
            return self.update_result
        return 'OK'

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if 'FROM auth_sessions' in query:
            return self.session_row
        if 'FROM user_entitlements' in query:
            user_id = str(args[0])
            return next(
                (row for row in self.entitlement_rows if str(row['user_id']) == user_id),
                None,
            )
        return None

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        if 'FROM user_entitlements' in query:
            wanted = set(args[0])
            return [row for row in self.entitlement_rows if str(row['user_id']) in wanted]
        return []


class FakeAuthPool:
    def __init__(self):
        self.connection = FakeAuthConnection()
        self.closed = False

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def close(self):
        self.closed = True


def test_guest_creation_persists_only_digest_and_defaults_free_for_30_days():
    async def scenario():
        now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        pool = FakeAuthPool()
        ids = iter(['user-1', 'session-1'])

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresAuthRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
            clock=lambda: now,
            token_factory=lambda: 'raw-bearer-token',
            id_factory=lambda: next(ids),
        )

        issued = await repository.create_guest_session()

        assert issued.user_id == 'user-1'
        assert issued.access_token == 'raw-bearer-token'
        assert issued.expires_at_epoch == int((now + timedelta(days=30)).timestamp())

        schema_queries = [query for query, _ in pool.connection.queries if 'CREATE TABLE' in query]
        assert len(schema_queries) == 3

        flattened_args = [value for _, args in pool.connection.queries for value in args]
        assert 'raw-bearer-token' not in flattened_args

        session_insert = next(
            (query, args)
            for query, args in pool.connection.queries
            if 'INSERT INTO auth_sessions' in query
        )
        assert session_insert[1][0] == 'session-1'
        assert session_insert[1][1] == 'user-1'
        assert session_insert[1][2] == hash_session_token('raw-bearer-token')
        assert session_insert[1][3] == now + timedelta(days=30)

        entitlement_insert = next(
            (query, args)
            for query, args in pool.connection.queries
            if 'INSERT INTO user_entitlements' in query
        )
        assert entitlement_insert[1] == ('user-1', EntitlementStatus.FREE.value)

        await repository.close()
        assert pool.closed is True

    asyncio.run(scenario())


def test_resolve_session_accepts_active_and_rejects_revoked_or_expired():
    async def scenario():
        now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        pool = FakeAuthPool()

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresAuthRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
            clock=lambda: now,
        )
        digest = hash_session_token('token')

        pool.connection.session_row = {
            'user_id': 'user-1',
            'expires_at': now + timedelta(hours=1),
            'revoked_at': None,
            'status': 'pro_active',
            'valid_until': now + timedelta(days=10),
        }
        principal = await repository.resolve_session(digest)
        assert principal is not None
        assert principal.user_id == 'user-1'
        assert principal.entitlement.status is EntitlementStatus.PRO_ACTIVE

        pool.connection.session_row = {
            'user_id': 'user-1',
            'expires_at': now + timedelta(hours=1),
            'revoked_at': now,
            'status': 'pro_active',
            'valid_until': now + timedelta(days=10),
        }
        assert await repository.resolve_session(digest) is None

        pool.connection.session_row = {
            'user_id': 'user-1',
            'expires_at': now - timedelta(seconds=1),
            'revoked_at': None,
            'status': 'pro_active',
            'valid_until': now + timedelta(days=10),
        }
        assert await repository.resolve_session(digest) is None

    asyncio.run(scenario())


def test_revoke_session_updates_by_digest_and_is_idempotent():
    async def scenario():
        now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        pool = FakeAuthPool()

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresAuthRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
            clock=lambda: now,
        )
        digest = hash_session_token('logout-token')

        assert await repository.revoke_session(digest) is True
        pool.connection.update_result = 'UPDATE 0'
        assert await repository.revoke_session(digest) is False

        revoke_queries = [
            (query, args)
            for query, args in pool.connection.queries
            if 'UPDATE auth_sessions' in query
        ]
        assert len(revoke_queries) == 2
        assert revoke_queries[0][1] == (digest, now)

    asyncio.run(scenario())


def test_bulk_entitlements_are_loaded_server_side_and_missing_users_are_omitted():
    async def scenario():
        now = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)
        pool = FakeAuthPool()
        pool.connection.entitlement_rows = [
            {'user_id': 'a', 'status': 'pro_active', 'valid_until': now + timedelta(days=3)},
            {'user_id': 'b', 'status': 'free', 'valid_until': None},
        ]

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresAuthRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
            clock=lambda: now,
        )

        result = await repository.get_entitlements(['a', 'b', 'missing'])

        assert result == {
            'a': Entitlement(EntitlementStatus.PRO_ACTIVE, now + timedelta(days=3)),
            'b': Entitlement(EntitlementStatus.FREE, None),
        }

    asyncio.run(scenario())
