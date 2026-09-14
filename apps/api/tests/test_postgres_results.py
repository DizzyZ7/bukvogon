import asyncio
from contextlib import asynccontextmanager

from bukvogon.domain.anti_cheat import VerificationStatus
from bukvogon.domain.ranked import RankedResult
from bukvogon.infrastructure.postgres_results import PostgresRaceResultRepository
from bukvogon.services.races import PersistedRaceResult


class FakeConnection:
    def __init__(self):
        self.queries = []
        self.fetch_rows = []

    async def execute(self, query, *args):
        self.queries.append((query, args))
        return 'OK'

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        return list(self.fetch_rows)


class FakePool:
    def __init__(self):
        self.connection = FakeConnection()
        self.closed = False

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def close(self):
        self.closed = True


def test_postgres_result_repository_is_lazy_idempotent_and_reuses_pool():
    async def scenario():
        pool = FakePool()
        calls = []

        async def pool_factory(**kwargs):
            calls.append(kwargs)
            return pool

        repository = PostgresRaceResultRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
        )

        first = PersistedRaceResult('race-1', 'a', 1, 420, 0.99)
        second = PersistedRaceResult('race-1', 'b', 2, 390, 0.97)

        await repository.persist(first)
        await repository.persist(second)

        assert len(calls) == 1
        assert calls[0]['min_size'] == 1
        assert calls[0]['max_size'] == 5

        schema_queries = [query for query, _ in pool.connection.queries if 'CREATE TABLE' in query]
        insert_queries = [query for query, _ in pool.connection.queries if 'INSERT INTO race_results' in query]

        assert len(schema_queries) == 1
        assert len(insert_queries) == 2
        assert 'ON CONFLICT (race_id, player_id)' in insert_queries[0]

        await repository.close()
        assert pool.closed is True

    asyncio.run(scenario())


def test_postgres_repository_loads_server_owned_ranked_results_for_rating():
    async def scenario():
        pool = FakePool()
        pool.connection.fetch_rows = [
            {'player_id': 'a', 'place': 1, 'verification_status': 'verified'},
            {'player_id': 'b', 'place': 2, 'verification_status': 'review'},
        ]

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresRaceResultRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
        )

        results = await repository.fetch_ranked_results('race-42')

        assert results == [
            RankedResult('a', 1, VerificationStatus.VERIFIED),
            RankedResult('b', 2, VerificationStatus.REVIEW),
        ]
        select_queries = [query for query, _ in pool.connection.queries if 'SELECT player_id' in query]
        assert len(select_queries) == 1
        assert 'WHERE race_id = $1' in select_queries[0]

        await repository.close()

    asyncio.run(scenario())
