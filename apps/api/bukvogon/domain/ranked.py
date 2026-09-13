from __future__ import annotations

from dataclasses import dataclass
from math import pow

from bukvogon.domain.entitlements import Entitlement, can_play_ranked


@dataclass(frozen=True, slots=True)
class RankedEligibility:
    allowed: bool
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class RankedPlayer:
    user_id: str
    rating: float


@dataclass(frozen=True, slots=True)
class RankedResult:
    user_id: str
    place: int


def check_ranked_eligibility(entitlement: Entitlement) -> RankedEligibility:
    if can_play_ranked(entitlement):
        return RankedEligibility(allowed=True)
    return RankedEligibility(allowed=False, reason="pro_required")


class MultiplayerEloEngine:
    def __init__(self, *, k_factor: float = 32.0) -> None:
        if k_factor <= 0:
            raise ValueError("k_factor must be positive")
        self.k_factor = float(k_factor)

    @staticmethod
    def _expected(rating_a: float, rating_b: float) -> float:
        return 1.0 / (1.0 + pow(10.0, (rating_b - rating_a) / 400.0))

    @staticmethod
    def _actual(place_a: int, place_b: int) -> float:
        if place_a < place_b:
            return 1.0
        if place_a > place_b:
            return 0.0
        return 0.5

    def rate(
        self,
        players: list[RankedPlayer],
        results: list[RankedResult],
    ) -> dict[str, float]:
        if len(players) < 2:
            raise ValueError("at least two players are required")

        player_ids = [player.user_id for player in players]
        result_ids = [result.user_id for result in results]
        if len(set(player_ids)) != len(player_ids):
            raise ValueError("player ids must be unique")
        if len(set(result_ids)) != len(result_ids):
            raise ValueError("result ids must be unique")
        if set(player_ids) != set(result_ids):
            raise ValueError("results must contain exactly one entry per player")
        if any(result.place < 1 for result in results):
            raise ValueError("places must be positive")

        by_result = {result.user_id: result for result in results}
        opponent_count = len(players) - 1
        deltas: dict[str, float] = {}

        for player in players:
            expected_sum = 0.0
            actual_sum = 0.0
            player_place = by_result[player.user_id].place

            for opponent in players:
                if opponent.user_id == player.user_id:
                    continue
                expected_sum += self._expected(player.rating, opponent.rating)
                actual_sum += self._actual(player_place, by_result[opponent.user_id].place)

            expected_average = expected_sum / opponent_count
            actual_average = actual_sum / opponent_count
            deltas[player.user_id] = self.k_factor * (actual_average - expected_average)

        return {player.user_id: player.rating + deltas[player.user_id] for player in players}
