from bukvogon.domain.anti_cheat import (
    TelemetryEvidence,
    TelemetryEvent,
    TelemetryKind,
    VerificationStatus,
    evaluate_evidence,
)


def _events(intervals: list[int], *, trusted: bool = True) -> tuple[TelemetryEvent, ...]:
    return tuple(
        TelemetryEvent(dt_ms=dt, kind=TelemetryKind.INSERT, trusted=trusted, delta=1)
        for dt in intervals
    )


def test_normal_varied_typing_is_verified():
    evidence = TelemetryEvidence(
        events=_events([92, 75, 121, 68, 104, 83, 139, 74, 97, 111, 66, 128]),
        accepted_characters=12,
        errors=1,
        corrections=1,
    )

    decision = evaluate_evidence(evidence)

    assert decision.status is VerificationStatus.VERIFIED
    assert decision.risk_score < 35
    assert decision.hard_invalid is False


def test_fast_but_varied_typing_is_not_invalidated_for_speed():
    evidence = TelemetryEvidence(
        events=_events([25, 37, 19, 42, 31, 23, 46, 28, 35, 21, 40, 27, 33, 24]),
        accepted_characters=14,
    )

    decision = evaluate_evidence(evidence)

    assert decision.status is VerificationStatus.VERIFIED
    assert 'high_speed' not in decision.reasons


def test_perfectly_periodic_scripted_timing_is_reviewed():
    evidence = TelemetryEvidence(
        events=_events([40] * 30),
        accepted_characters=30,
    )

    decision = evaluate_evidence(evidence)

    assert decision.status is VerificationStatus.REVIEW
    assert decision.risk_score >= 35
    assert 'periodic_timing' in decision.reasons


def test_sparse_telemetry_is_reviewed_not_banned():
    evidence = TelemetryEvidence(
        events=_events([90, 80, 110, 95, 75, 120]),
        accepted_characters=10,
    )

    decision = evaluate_evidence(evidence)

    assert decision.status is VerificationStatus.REVIEW
    assert decision.hard_invalid is False
    assert 'low_telemetry_coverage' in decision.reasons


def test_paste_that_advances_ranked_text_is_invalid():
    evidence = TelemetryEvidence(
        events=(
            TelemetryEvent(dt_ms=100, kind=TelemetryKind.INSERT, trusted=True, delta=1),
            TelemetryEvent(dt_ms=20, kind=TelemetryKind.PASTE, trusted=True, delta=8),
        ),
        accepted_characters=9,
    )

    decision = evaluate_evidence(evidence)

    assert decision.status is VerificationStatus.INVALID
    assert decision.hard_invalid is True
    assert 'paste_advanced_text' in decision.reasons


def test_claimed_progress_without_enough_insert_evidence_is_invalid():
    evidence = TelemetryEvidence(
        events=_events([80, 90, 70]),
        accepted_characters=8,
    )

    decision = evaluate_evidence(evidence)

    assert decision.status is VerificationStatus.INVALID
    assert decision.hard_invalid is True
    assert 'progress_event_mismatch' in decision.reasons


def test_mostly_untrusted_input_raises_risk_without_being_single_signal_ban():
    evidence = TelemetryEvidence(
        events=_events([80, 91, 73, 101, 84, 95, 77, 109, 88, 99], trusted=False),
        accepted_characters=10,
    )

    decision = evaluate_evidence(evidence)

    assert decision.status is VerificationStatus.REVIEW
    assert decision.hard_invalid is False
    assert 'mostly_untrusted_events' in decision.reasons
