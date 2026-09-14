import asyncio

from bukvogon.domain.anti_cheat import (
    TelemetryEvidence,
    TelemetryEvent,
    TelemetryKind,
    VerificationStatus,
)
from bukvogon.infrastructure.redis_anti_cheat import AntiCheatState
from bukvogon.services.anti_cheat import RankedAntiCheatService


class FakeAntiCheatStore:
    def __init__(self, evidence: TelemetryEvidence):
        self.evidence = evidence
        self.finalized = False
        self.state = AntiCheatState(
            challenge_id='challenge-1',
            race_id='race-1',
            player_id='player-1',
            target_text='кот',
            last_seq=3,
            finalized=False,
        )

    async def get_state(self, challenge_id: str):
        assert challenge_id == 'challenge-1'
        return AntiCheatState(
            challenge_id=self.state.challenge_id,
            race_id=self.state.race_id,
            player_id=self.state.player_id,
            target_text=self.state.target_text,
            last_seq=self.state.last_seq,
            finalized=self.finalized,
        )

    async def get_evidence(self, challenge_id: str):
        assert challenge_id == 'challenge-1'
        return self.evidence

    async def finalize(self, challenge_id: str):
        assert challenge_id == 'challenge-1'
        self.finalized = True


class FakeVerificationRepository:
    def __init__(self):
        self.updates = []

    async def update_verification(self, race_id, player_id, decision, *, audit_trace=None):
        self.updates.append((race_id, player_id, decision, audit_trace))


def _human_evidence():
    intervals = [91, 73, 122, 68, 107, 82, 135, 76, 98, 113]
    return TelemetryEvidence(
        events=tuple(
            TelemetryEvent(dt_ms=value, kind=TelemetryKind.INSERT, trusted=True, delta=1)
            for value in intervals
        ),
        accepted_characters=len(intervals),
        errors=1,
        corrections=1,
    )


def test_finish_verification_promotes_human_like_result_to_verified_and_finalizes_challenge():
    async def scenario():
        store = FakeAntiCheatStore(_human_evidence())
        repository = FakeVerificationRepository()
        service = RankedAntiCheatService(store=store, result_repository=repository)

        decision = await service.verify_finish('challenge-1')

        assert decision.status is VerificationStatus.VERIFIED
        assert store.finalized is True
        assert len(repository.updates) == 1
        assert repository.updates[0][0:2] == ('race-1', 'player-1')
        assert repository.updates[0][2].status is VerificationStatus.VERIFIED

    asyncio.run(scenario())


def test_finish_verification_keeps_periodic_script_out_of_verified_state():
    async def scenario():
        evidence = TelemetryEvidence(
            events=tuple(
                TelemetryEvent(dt_ms=40, kind=TelemetryKind.INSERT, trusted=True, delta=1)
                for _ in range(30)
            ),
            accepted_characters=30,
        )
        store = FakeAntiCheatStore(evidence)
        repository = FakeVerificationRepository()
        service = RankedAntiCheatService(store=store, result_repository=repository)

        decision = await service.verify_finish('challenge-1')

        assert decision.status is VerificationStatus.REVIEW
        assert repository.updates[0][2].status is VerificationStatus.REVIEW

    asyncio.run(scenario())


def test_verification_can_be_retried_idempotently_after_finalize():
    async def scenario():
        store = FakeAntiCheatStore(_human_evidence())
        repository = FakeVerificationRepository()
        service = RankedAntiCheatService(store=store, result_repository=repository)

        first = await service.verify_finish('challenge-1')
        second = await service.verify_finish('challenge-1')

        assert first == second
        assert len(repository.updates) == 2
        assert all(update[2].status is VerificationStatus.VERIFIED for update in repository.updates)

    asyncio.run(scenario())
