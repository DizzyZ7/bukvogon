from __future__ import annotations

import json
from typing import Protocol

from bukvogon.domain.anti_cheat import AntiCheatDecision, TelemetryEvidence, evaluate_evidence
from bukvogon.infrastructure.redis_anti_cheat import AntiCheatState

VERIFIER_VERSION = 'v1'
MAX_AUDIT_TRACE_BYTES = 64 * 1024


class AntiCheatStore(Protocol):
    async def get_state(self, challenge_id: str) -> AntiCheatState: ...
    async def get_evidence(self, challenge_id: str) -> TelemetryEvidence: ...
    async def finalize(self, challenge_id: str) -> None: ...


class VerificationRepository(Protocol):
    async def update_verification(
        self,
        race_id: str,
        player_id: str,
        decision: AntiCheatDecision,
        *,
        audit_trace: bytes | None = None,
    ) -> None: ...


def _compact_audit_trace(evidence: TelemetryEvidence, decision: AntiCheatDecision) -> bytes:
    payload = {
        'verifier_version': VERIFIER_VERSION,
        'event_count': len(evidence.events),
        'accepted_characters': evidence.accepted_characters,
        'errors': evidence.errors,
        'corrections': evidence.corrections,
        'risk_score': decision.risk_score,
        'reasons': list(decision.reasons),
        'telemetry_coverage': round(decision.telemetry_coverage, 4),
        'timings_ms': [event.dt_ms for event in evidence.events],
        'kinds': [event.kind.value for event in evidence.events],
        'trusted': [event.trusted for event in evidence.events],
        'deltas': [event.delta for event in evidence.events],
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
    if len(encoded) > MAX_AUDIT_TRACE_BYTES:
        raise ValueError('anti-cheat audit trace exceeds storage bound')
    return encoded


class RankedAntiCheatService:
    def __init__(self, *, store: AntiCheatStore, result_repository: VerificationRepository) -> None:
        self._store = store
        self._result_repository = result_repository

    async def verify_finish(self, challenge_id: str) -> AntiCheatDecision:
        state = await self._store.get_state(challenge_id)
        evidence = await self._store.get_evidence(challenge_id)
        decision = evaluate_evidence(evidence)
        audit_trace = _compact_audit_trace(evidence, decision)

        if not state.finalized:
            await self._store.finalize(challenge_id)

        await self._result_repository.update_verification(
            state.race_id,
            state.player_id,
            decision,
            audit_trace=audit_trace,
        )
        return decision
