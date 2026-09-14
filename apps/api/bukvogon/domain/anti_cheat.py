from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from enum import StrEnum
import math
import statistics


class VerificationStatus(StrEnum):
    PROVISIONAL = 'provisional'
    VERIFIED = 'verified'
    REVIEW = 'review'
    INVALID = 'invalid'


class TelemetryKind(StrEnum):
    INSERT = 'insert'
    DELETE = 'delete'
    COMPOSITION = 'composition'
    PASTE = 'paste'
    DROP = 'drop'
    OTHER = 'other'


@dataclass(frozen=True, slots=True)
class TelemetryEvent:
    dt_ms: int
    kind: TelemetryKind
    trusted: bool
    delta: int
    input_type: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.dt_ms, bool) or not isinstance(self.dt_ms, int) or not 0 <= self.dt_ms <= 60_000:
            raise ValueError('dt_ms must be an integer between 0 and 60000')
        if isinstance(self.delta, bool) or not isinstance(self.delta, int) or not -32 <= self.delta <= 32:
            raise ValueError('delta must be an integer between -32 and 32')


@dataclass(frozen=True, slots=True)
class TelemetryEvidence:
    events: tuple[TelemetryEvent, ...]
    accepted_characters: int
    errors: int = 0
    corrections: int = 0
    observed_characters: int | None = None
    elapsed_ms: int | None = None
    hard_reasons: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.accepted_characters < 0:
            raise ValueError('accepted_characters cannot be negative')
        if self.errors < 0 or self.corrections < 0:
            raise ValueError('error counters cannot be negative')

        observed = self.observed_characters
        if observed is None:
            observed = _progress_evidence(self.events)
            object.__setattr__(self, 'observed_characters', observed)
        if observed < 0:
            raise ValueError('observed_characters cannot be negative')

        elapsed = self.elapsed_ms
        if elapsed is None:
            elapsed = sum(event.dt_ms for event in self.events)
            object.__setattr__(self, 'elapsed_ms', elapsed)
        if elapsed < 0:
            raise ValueError('elapsed_ms cannot be negative')

        if any(not reason for reason in self.hard_reasons):
            raise ValueError('hard reasons must be non-empty strings')


@dataclass(frozen=True, slots=True)
class AntiCheatDecision:
    status: VerificationStatus
    risk_score: int
    reasons: tuple[str, ...]
    hard_invalid: bool
    telemetry_coverage: float


def _progress_evidence(events: tuple[TelemetryEvent, ...]) -> int:
    return sum(
        max(event.delta, 0)
        for event in events
        if event.kind in {TelemetryKind.INSERT, TelemetryKind.COMPOSITION}
    )


def _coverage(evidence: TelemetryEvidence) -> float:
    if evidence.accepted_characters == 0:
        return 1.0
    observed = evidence.observed_characters or 0
    return min(1.0, observed / evidence.accepted_characters)


def _periodicity_risk(events: tuple[TelemetryEvent, ...]) -> tuple[int, list[str]]:
    intervals = [event.dt_ms for event in events if event.kind is TelemetryKind.INSERT and event.dt_ms > 0]
    if len(intervals) < 10:
        return 0, []

    counts = Counter(intervals)
    repeated_ratio = max(counts.values()) / len(intervals)
    median = statistics.median(intervals)
    mad = statistics.median(abs(value - median) for value in intervals)

    score = 0
    reasons: list[str] = []
    if repeated_ratio >= 0.8 or mad <= 1:
        score += 50
        reasons.append('periodic_timing')
    elif repeated_ratio >= 0.55 or mad <= 3:
        score += 25
        reasons.append('low_timing_diversity')
    return score, reasons


def evaluate_evidence(evidence: TelemetryEvidence) -> AntiCheatDecision:
    reasons: list[str] = list(evidence.hard_reasons)
    hard_invalid = bool(evidence.hard_reasons)
    risk = 0

    for event in evidence.events:
        if event.kind is TelemetryKind.PASTE and event.delta > 0:
            reasons.append('paste_advanced_text')
            hard_invalid = True
        elif event.kind is TelemetryKind.DROP and event.delta > 0:
            reasons.append('drop_advanced_text')
            hard_invalid = True

    coverage = _coverage(evidence)
    if evidence.accepted_characters > 0 and coverage < 0.5:
        reasons.append('progress_event_mismatch')
        hard_invalid = True
    elif coverage < 0.8:
        reasons.append('low_telemetry_coverage')
        risk += 40

    timing_risk, timing_reasons = _periodicity_risk(evidence.events)
    risk += timing_risk
    reasons.extend(timing_reasons)

    if evidence.events:
        untrusted_ratio = sum(not event.trusted for event in evidence.events) / len(evidence.events)
        if untrusted_ratio >= 0.8:
            risk += 40
            reasons.append('mostly_untrusted_events')
        elif untrusted_ratio >= 0.4:
            risk += 20
            reasons.append('many_untrusted_events')

    # A long error-free run is deliberately weak evidence. Fast or accurate typists
    # must not be penalized simply for being good at the game.
    if evidence.accepted_characters >= 60 and evidence.errors == 0 and evidence.corrections == 0:
        risk += 5
        reasons.append('long_perfect_run')

    if not math.isfinite(float(risk)):
        risk = 100
    risk_score = max(0, min(100, int(risk)))

    if hard_invalid:
        status = VerificationStatus.INVALID
    elif risk_score < 35:
        status = VerificationStatus.VERIFIED
    else:
        status = VerificationStatus.REVIEW

    return AntiCheatDecision(
        status=status,
        risk_score=risk_score,
        reasons=tuple(dict.fromkeys(reasons)),
        hard_invalid=hard_invalid,
        telemetry_coverage=coverage,
    )
