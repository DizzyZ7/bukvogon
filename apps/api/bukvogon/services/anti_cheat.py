from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Protocol

from bukvogon.domain.anti_cheat import AntiCheatDecision, TelemetryEvidence, evaluate_evidence
from bukvogon.domain.race_protocol import RankedTelemetryBatch
from bukvogon.infrastructure.redis_anti_cheat import AntiCheatState, RankedChallenge

VERIFIER_VERSION = 'v1'
MAX_AUDIT_TRACE_BYTES = 64 * 1024


@dataclass(frozen=True, slots=True)
class AcceptedRankedProgress:
    offset: int
    cpm: int
    accuracy: float


class AntiCheatStore(Protocol):
    async def issue_challenge(self, race_id: str, player_id: str, *, target_text: str) -> RankedChallenge: ...
    async def get_state(self, challenge_id: str) -> AntiCheatState: ...
    async def validate_and_advance(
        self,
        challenge_id: str,
        *,
        race_id: str,
        player_id: str,
        nonce: str,
        batch_seq: int,
    ) -> AntiCheatState: ...
    async def append_evidence(
        self,
        challenge_id: str,
        *,
        events: tuple,
        accepted_characters: int,
        errors: int,
        corrections: int,
        focused: bool,
        visible: bool,
    ) -> None: ...
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


def _server_metrics(evidence: TelemetryEvidence) -> AcceptedRankedProgress:
    elapsed_ms = sum(event.dt_ms for event in evidence.events)
    cpm = 0 if elapsed_ms <= 0 else round(evidence.accepted_characters * 60_000 / elapsed_ms)
    attempts = evidence.accepted_characters + evidence.errors
    accuracy = 1.0 if attempts <= 0 else evidence.accepted_characters / attempts
    return AcceptedRankedProgress(
        offset=evidence.accepted_characters,
        cpm=max(0, cpm),
        accuracy=max(0.0, min(1.0, accuracy)),
    )


class RankedAntiCheatService:
    def __init__(self, *, store: AntiCheatStore, result_repository: VerificationRepository) -> None:
        self._store = store
        self._result_repository = result_repository

    async def issue_challenge(self, race_id: str, player_id: str, *, target_text: str) -> RankedChallenge:
        return await self._store.issue_challenge(race_id, player_id, target_text=target_text)

    async def accept_batch(
        self,
        race_id: str,
        player_id: str,
        batch: RankedTelemetryBatch,
    ) -> AcceptedRankedProgress:
        state = await self._store.get_state(batch.challenge_id)
        if state.race_id != race_id or state.player_id != player_id:
            raise ValueError('challenge binding mismatch')
        if state.finalized:
            raise ValueError('challenge finalized')
        if batch.batch_seq != state.last_seq + 1:
            raise ValueError('batch sequence mismatch')

        previous = await self._store.get_evidence(batch.challenge_id)
        if batch.fragment_start != previous.accepted_characters:
            raise ValueError('fragment start does not match server progress')
        if batch.offset > len(state.target_text):
            raise ValueError('ranked progress exceeds target text')
        expected_fragment = state.target_text[batch.fragment_start:batch.offset]
        if batch.fragment != expected_fragment:
            raise ValueError('fragment does not match target text')

        await self._store.validate_and_advance(
            batch.challenge_id,
            race_id=race_id,
            player_id=player_id,
            nonce=batch.nonce,
            batch_seq=batch.batch_seq,
        )
        await self._store.append_evidence(
            batch.challenge_id,
            events=batch.events,
            accepted_characters=batch.offset,
            errors=batch.errors,
            corrections=batch.corrections,
            focused=batch.focused,
            visible=batch.visible,
        )
        evidence = await self._store.get_evidence(batch.challenge_id)
        return _server_metrics(evidence)

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
