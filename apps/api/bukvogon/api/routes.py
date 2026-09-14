from __future__ import annotations

from fastapi import APIRouter

from bukvogon.api.models import (
    AccessResponse,
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
