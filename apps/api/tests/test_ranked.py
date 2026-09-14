import pytest

from bukvogon.domain.anti_cheat import VerificationStatus
from bukvogon.domain.entitlements import Entitlement, EntitlementStatus
from bukvogon.domain.ranked import (
    MultiplayerEloEngine,
    RankedPlayer,
    RankedResult,
    check_competitive_result_eligibility,
    check_ranked_eligibility,
)


def test_free_user_is_rejected_from_ranked():
    eligibility = check_ranked_eligibility(Entitlement(status=EntitlementStatus.FREE))
    assert eligibility.allowed is False
    assert eligibility.reason == "pro_required"


def test_active_pro_user_is_allowed_into_ranked():
    eligibility = check_ranked_eligibility(Entitlement(status=EntitlementStatus.PRO_ACTIVE))
    assert eligibility.allowed is True
    assert eligibility.reason is None


def _verified(user_id: str, place: int) -> RankedResult:
    return RankedResult(user_id, place, VerificationStatus.VERIFIED)


def test_verified_result_counts_for_all_competitive_surfaces():
    eligibility = check_competitive_result_eligibility(VerificationStatus.VERIFIED)

    assert eligibility.counts_for_mmr is True
    assert eligibility.visible_on_leaderboard is True
    assert eligibility.eligible_for_top_1000 is True
    assert eligibility.reason is None


@pytest.mark.parametrize(
    'verification_status',
    [
        VerificationStatus.PROVISIONAL,
        VerificationStatus.REVIEW,
        VerificationStatus.INVALID,
    ],
)
def test_unverified_result_is_excluded_from_all_competitive_surfaces(verification_status):
    eligibility = check_competitive_result_eligibility(verification_status)

    assert eligibility.counts_for_mmr is False
    assert eligibility.visible_on_leaderboard is False
    assert eligibility.eligible_for_top_1000 is False
    assert eligibility.reason == 'verified_result_required'


def test_multiplayer_elo_rewards_first_and_penalizes_last():
    engine = MultiplayerEloEngine(k_factor=32)
    players = [
        RankedPlayer("a", 1000),
        RankedPlayer("b", 1000),
        RankedPlayer("c", 1000),
        RankedPlayer("d", 1000),
    ]
    results = [
        _verified("a", 1),
        _verified("b", 2),
        _verified("c", 3),
        _verified("d", 4),
    ]

    rated = engine.rate(players, results)

    assert rated["a"] > 1000
    assert rated["d"] < 1000
    assert rated["a"] > rated["b"] > rated["c"] > rated["d"]
    assert sum(rated[p.user_id] - p.rating for p in players) == pytest.approx(0.0)


def test_rating_is_deterministic_for_same_match():
    engine = MultiplayerEloEngine(k_factor=24)
    players = [RankedPlayer("a", 1100), RankedPlayer("b", 1000), RankedPlayer("c", 900)]
    results = [_verified("c", 1), _verified("b", 2), _verified("a", 3)]

    assert engine.rate(players, results) == engine.rate(players, results)


def test_tied_players_receive_equal_actual_score_against_each_other():
    engine = MultiplayerEloEngine(k_factor=32)
    players = [RankedPlayer("a", 1000), RankedPlayer("b", 1000), RankedPlayer("c", 1000)]
    results = [_verified("a", 1), _verified("b", 1), _verified("c", 3)]

    rated = engine.rate(players, results)

    assert rated["a"] == pytest.approx(rated["b"])
    assert rated["a"] > 1000
    assert rated["c"] < 1000


def test_rating_requires_exactly_one_result_per_player():
    engine = MultiplayerEloEngine()
    players = [RankedPlayer("a", 1000), RankedPlayer("b", 1000)]

    with pytest.raises(ValueError):
        engine.rate(players, [_verified("a", 1)])


@pytest.mark.parametrize(
    'verification_status',
    [
        VerificationStatus.PROVISIONAL,
        VerificationStatus.REVIEW,
        VerificationStatus.INVALID,
    ],
)
def test_rating_rejects_any_result_that_is_not_verified(verification_status):
    engine = MultiplayerEloEngine()
    players = [RankedPlayer('a', 1000), RankedPlayer('b', 1000)]
    results = [
        RankedResult('a', 1, VerificationStatus.VERIFIED),
        RankedResult('b', 2, verification_status),
    ]

    with pytest.raises(ValueError, match='verified results'):
        engine.rate(players, results)
