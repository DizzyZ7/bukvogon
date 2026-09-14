from __future__ import annotations

from fastapi import APIRouter, HTTPException

from bukvogon.api.models import (
    AccessResponse,
    RankedRateRequest,
    RankedRateResponse,
    TypingValidationRequest,
    TypingValidationResponse,
)
from bukvogon.domain.entitlements import (
    Entitlement,
    EntitlementStatus,
    can_play_ranked,
    can_view_leaderboard,
)
from bukvogon.domain.ranked import MultiplayerEloEngine, RankedPlayer, RankedResult
from bukvogon.domain.typing import validate_typed_prefix

router = APIRouter()


@router.get('/access/{status}', response_model=AccessResponse)
def access(status: EntitlementStatus) -> AccessResponse:
    entitlement = Entitlement(status=status)
    return AccessResponse(
        casual=True,
        ranked=can_play_ranked(entitlement),
        leaderboard=can_view_leaderboard(entitlement),
    )


@router.post('/typing/validate', response_model=TypingValidationResponse)
def typing_validate(payload: TypingValidationRequest) -> TypingValidationResponse:
    result = validate_typed_prefix(payload.target, payload.typed, payload.mode)
    return TypingValidationResponse(
        valid=result.valid,
        matched_characters=result.matched_characters,
        error_index=result.error_index,
    )


@router.post('/ranked/rate', response_model=RankedRateResponse)
def ranked_rate(payload: RankedRateRequest) -> RankedRateResponse:
    engine = MultiplayerEloEngine(k_factor=payload.k_factor)
    try:
        ratings = engine.rate(
            [RankedPlayer(player.user_id, player.rating) for player in payload.players],
            [
                RankedResult(result.user_id, result.place, result.verification_status)
                for result in payload.results
            ],
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RankedRateResponse(ratings=ratings)
