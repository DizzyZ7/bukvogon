from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import StrEnum


class EntitlementStatus(StrEnum):
    FREE = "free"
    PRO_ACTIVE = "pro_active"
    PRO_GRACE = "pro_grace"
    PRO_EXPIRED = "pro_expired"


@dataclass(frozen=True, slots=True)
class Entitlement:
    status: EntitlementStatus
    valid_until: datetime | None = None

    def is_current(self, *, now: datetime | None = None) -> bool:
        if self.status is not EntitlementStatus.PRO_ACTIVE:
            return False
        if self.valid_until is None:
            return True
        current_time = now or datetime.now(timezone.utc)
        deadline = self.valid_until
        if deadline.tzinfo is None:
            deadline = deadline.replace(tzinfo=timezone.utc)
        return deadline > current_time


def can_play_ranked(entitlement: Entitlement, *, now: datetime | None = None) -> bool:
    return entitlement.is_current(now=now)


def can_view_leaderboard(entitlement: Entitlement, *, now: datetime | None = None) -> bool:
    return entitlement.is_current(now=now)
