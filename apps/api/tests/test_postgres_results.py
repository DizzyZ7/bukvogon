import asyncio
from contextlib import asynccontextmanager

from bukvogon.infrastructure.postgres_results import PostgresRaceResultRepository
from bukvogon.services.races import PersistedRaceResult


class FakeConnection:
    def __init__(self):
        self.queries = []

    async def execute(self, query, *args):
        self.queries.append((query, args))
        return 'OK'


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
