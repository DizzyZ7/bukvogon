import pytest

from bukvogon.domain.entitlements import Entitlement, EntitlementStatus
from bukvogon.domain.ranked import (
    MultiplayerEloEngine,
    RankedPlayer,
    RankedResult,
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


def test_multiplayer_elo_rewards_first_and_penalizes_last():
    engine = MultiplayerEloEngine(k_factor=32)
    players = [
        RankedPlayer("a", 1000),
        RankedPlayer("b", 1000),
        RankedPlayer("c", 1000),
        RankedPlayer("d", 1000),
    ]
    results = [
        RankedResult("a", 1),
        RankedResult("b", 2),
        RankedResult("c", 3),
        RankedResult("d", 4),
    ]

    rated = engine.rate(players, results)

    assert rated["a"] > 1000
    assert rated["d"] < 1000
    assert rated["a"] > rated["b"] > rated["c"] > rated["d"]
    assert sum(rated[p.user_id] - p.rating for p in players) == pytest.approx(0.0)


def test_rating_is_deterministic_for_same_match():
    engine = MultiplayerEloEngine(k_factor=24)
    players = [RankedPlayer("a", 1100), RankedPlayer("b", 1000), RankedPlayer("c", 900)]
    results = [RankedResult("c", 1), RankedResult("b", 2), RankedResult("a", 3)]

    assert engine.rate(players, results) == engine.rate(players, results)


def test_tied_players_receive_equal_actual_score_against_each_other():
    engine = MultiplayerEloEngine(k_factor=32)
    players = [RankedPlayer("a", 1000), RankedPlayer("b", 1000), RankedPlayer("c", 1000)]
    results = [RankedResult("a", 1), RankedResult("b", 1), RankedResult("c", 3)]

    rated = engine.rate(players, results)

    assert rated["a"] == pytest.approx(rated["b"])
    assert rated["a"] > 1000
    assert rated["c"] < 1000


def test_rating_requires_exactly_one_result_per_player():
    engine = MultiplayerEloEngine()
    players = [RankedPlayer("a", 1000), RankedPlayer("b", 1000)]

    with pytest.raises(ValueError):
        engine.rate(players, [RankedResult("a", 1)])
