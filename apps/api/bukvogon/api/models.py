from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

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


class RankedRateRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')

    race_id: str = Field(min_length=1)


class RankedRateResponse(BaseModel):
    ratings: dict[str, float]
    applied: bool
