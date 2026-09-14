import asyncio
from contextlib import asynccontextmanager

from bukvogon.domain.anti_cheat import VerificationStatus
from bukvogon.domain.ranked import RankedResult
from bukvogon.infrastructure.postgres_results import PostgresRaceResultRepository
from bukvogon.services.races import PersistedRaceResult


class FakeTransaction:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


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


class RatingConnection(FakeConnection):
    def __init__(self):
        super().__init__()
        self.race_rows = [
            {'player_id': 'a', 'place': 1, 'verification_status': 'verified'},
            {'player_id': 'b', 'place': 2, 'verification_status': 'verified'},
        ]
        self.ratings = {}
        self.games_played = {}
        self.applied_races = set()

    def transaction(self):
        return FakeTransaction()

    async def execute(self, query, *args):
        self.queries.append((query, args))
        if 'INSERT INTO ranked_player_ratings' in query:
            player_id = str(args[0])
            self.ratings.setdefault(player_id, 1000.0)
            self.games_played.setdefault(player_id, 0)
        elif 'UPDATE ranked_player_ratings' in query:
            player_id = str(args[0])
            self.ratings[player_id] = float(args[1])
            self.games_played[player_id] = self.games_played.get(player_id, 0) + 1
        return 'OK'

    async def fetch(self, query, *args):
        self.queries.append((query, args))
        if 'FROM race_results' in query:
            return list(self.race_rows)
        if 'FROM ranked_player_ratings' in query:
            player_ids = list(args[0])
            return [
                {
                    'player_id': player_id,
                    'rating': self.ratings[player_id],
                    'games_played': self.games_played[player_id],
                }
                for player_id in player_ids
                if player_id in self.ratings
            ]
        return []

    async def fetchrow(self, query, *args):
        self.queries.append((query, args))
        if 'INSERT INTO ranked_race_rating_applications' not in query:
            return None
        race_id = str(args[0])
        if race_id in self.applied_races:
            return None
        self.applied_races.add(race_id)
        return {'race_id': race_id}


class RatingPool(FakePool):
    def __init__(self):
        self.connection = RatingConnection()
        self.closed = False


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

        assert len(schema_queries) == 3
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


def test_ranked_rating_application_is_persistent_and_idempotent():
    async def scenario():
        pool = RatingPool()

        async def pool_factory(**_kwargs):
            return pool

        repository = PostgresRaceResultRepository(
            'postgresql://bukvogon:test@postgres/bukvogon',
            pool_factory=pool_factory,
        )

        first = await repository.apply_ranked_rating('race-verified')
        second = await repository.apply_ranked_rating('race-verified')

        assert first.applied is True
        assert first.ratings['a'] == 1016.0
        assert first.ratings['b'] == 984.0
        assert second.applied is False
        assert second.ratings == first.ratings
        assert pool.connection.games_played == {'a': 1, 'b': 1}

        claim_queries = [
            query for query, _ in pool.connection.queries
            if 'INSERT INTO ranked_race_rating_applications' in query
        ]
        assert len(claim_queries) == 2
        assert 'ON CONFLICT (race_id) DO NOTHING' in claim_queries[0]

        await repository.close()

    asyncio.run(scenario())
