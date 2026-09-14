import asyncio
from contextlib import asynccontextmanager

from bukvogon.domain.anti_cheat import AntiCheatDecision, VerificationStatus
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

    @asynccontextmanager
    async def acquire(self):
        yield self.connection

    async def close(self):
        return None


def test_finished_race_result_defaults_to_provisional():
    result = PersistedRaceResult('race-1', 'player-1', 1, 420, 0.99)

    assert result.verification_status is VerificationStatus.PROVISIONAL


def test_repository_persists_provisional_then_updates_verification_once_per_result_row():
    async def scenario():
        pool = FakePool()

        async def pool_factory(**_):
            return pool

        repository = PostgresRaceResultRepository('postgresql://test', pool_factory=pool_factory)
        result = PersistedRaceResult('race-1', 'player-1', 1, 420, 0.99)
        decision = AntiCheatDecision(
            status=VerificationStatus.VERIFIED,
            risk_score=8,
            reasons=('timing_ok',),
            hard_invalid=False,
            telemetry_coverage=1.0,
        )

        await repository.persist(result)
        await repository.update_verification('race-1', 'player-1', decision, audit_trace=b'compact-trace')

        schema = [query for query, _ in pool.connection.queries if 'CREATE TABLE' in query][0]
        insert = [item for item in pool.connection.queries if 'INSERT INTO race_results' in item[0]][0]
        update = [item for item in pool.connection.queries if 'UPDATE race_results' in item[0]][0]

        assert 'verification_status' in schema
        assert 'risk_score' in schema
        assert 'audit_trace' in schema
        assert VerificationStatus.PROVISIONAL.value in insert[1]
        assert VerificationStatus.VERIFIED.value in update[1]
        assert b'compact-trace' in update[1]

    asyncio.run(scenario())
