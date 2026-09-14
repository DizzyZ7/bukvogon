from datetime import datetime, timedelta, timezone

from bukvogon.domain.entitlements import (
    Entitlement,
    EntitlementStatus,
    can_play_ranked,
    can_view_leaderboard,
)


def test_free_cannot_play_ranked_or_view_leaderboard():
    entitlement = Entitlement(status=EntitlementStatus.FREE)
    assert can_play_ranked(entitlement) is False
    assert can_view_leaderboard(entitlement) is False


def test_active_pro_can_play_ranked_and_view_leaderboard():
    entitlement = Entitlement(
        status=EntitlementStatus.PRO_ACTIVE,
        valid_until=datetime.now(timezone.utc) + timedelta(days=30),
    )
    assert can_play_ranked(entitlement) is True
    assert can_view_leaderboard(entitlement) is True


def test_expired_pro_cannot_play_ranked_or_view_leaderboard():
    entitlement = Entitlement(
        status=EntitlementStatus.PRO_EXPIRED,
        valid_until=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert can_play_ranked(entitlement) is False
    assert can_view_leaderboard(entitlement) is False


def test_active_status_with_elapsed_valid_until_is_treated_as_expired():
    entitlement = Entitlement(
        status=EntitlementStatus.PRO_ACTIVE,
        valid_until=datetime.now(timezone.utc) - timedelta(seconds=1),
    )
    assert can_play_ranked(entitlement) is False
