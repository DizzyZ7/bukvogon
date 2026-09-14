from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

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
async def ranked_rate(payload: RankedRateRequest, request: Request) -> RankedRateResponse:
    result_repository = request.app.state.race_results
    try:
        application = await result_repository.apply_ranked_rating(payload.race_id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return RankedRateResponse(
        ratings=application.ratings,
        applied=application.applied,
    )
