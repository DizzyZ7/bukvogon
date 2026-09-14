from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from bukvogon.domain.anti_cheat import VerificationStatus
from bukvogon.domain.typing import TypingMode


class AccessResponse(BaseModel):
    casual: bool
    ranked: bool
    leaderboard: bool
    monthly_price_rub: int = 300


class TypingValidationRequest(BaseModel):
    target: str = Field(min_length=1)
    typed: str
    mode: TypingMode


class TypingValidationResponse(BaseModel):
    valid: bool
    matched_characters: int
    error_index: int | None


class RankedPlayerPayload(BaseModel):
    user_id: str = Field(min_length=1)
    rating: float


class RankedResultPayload(BaseModel):
    user_id: str = Field(min_length=1)
    place: int = Field(ge=1)
    verification_status: VerificationStatus


class RankedRateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    race_id: str = Field(min_length=1)
    players: list[RankedPlayerPayload] = Field(min_length=2)
    k_factor: float = Field(default=32.0, gt=0)


class RankedRateResponse(BaseModel):
    ratings: dict[str, float]
