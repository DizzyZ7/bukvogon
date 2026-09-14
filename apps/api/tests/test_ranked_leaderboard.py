import asyncio
from contextlib import asynccontextmanager

import pytest

from bukvogon.domain.ranked import RankedLeaderboardEntry
from bukvogon.infrastructure.postgres_results import PostgresRaceResultRepository


class FakeLeaderboardConnection:
    def __init__(self):
        self.queries = []

    async def execute(self, query, *args):
        self.queries.append((query, args))
        return 'OK'

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        if 'ROW_NUMBER()' not in query:
            return []
        return [
            {'player_id': 'alpha', 'rating': 1420.0, 'games_played': 31, 'position': 1},
            {'player_id': 'beta', 'rating': 1390.5, 'games_played': 28, 'position': 2},
        ]


class FakeLeaderboardPool:
    def __init__(self):
        self.connection = FakeLeaderboardConnection()
        self.closed = False

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def close(self):
        self.closed = True


def test_official_leaderboard_is_server_ranked_and_top_1000_is_derived_from_position():
    async def scenario():
        pool = FakeLeaderboardPool()

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresRaceResultRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
        )

        entries = await repository.fetch_ranked_leaderboard(limit=1000)

        assert entries == [
            RankedLeaderboardEntry('alpha', 1420.0, 31, 1),
            RankedLeaderboardEntry('beta', 1390.5, 28, 2),
        ]
        assert entries[0].is_top_1000 is True
        leaderboard_queries = [
            (query, args)
            for query, args in pool.connection.queries
            if 'ROW_NUMBER()' in query
        ]
        assert len(leaderboard_queries) == 1
        query, args = leaderboard_queries[0]
        assert 'ORDER BY rating DESC, games_played DESC, player_id ASC' in query
        assert args == (1000,)

        await repository.close()

    asyncio.run(scenario())


def test_leaderboard_limit_is_bounded_to_top_1000():
    async def scenario():
        pool = FakeLeaderboardPool()

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresRaceResultRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
        )

        with pytest.raises(ValueError, match='between 1 and 1000'):
            await repository.fetch_ranked_leaderboard(limit=1001)

        await repository.close()

    asyncio.run(scenario())
