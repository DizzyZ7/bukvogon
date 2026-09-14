from __future__ import annotations

from pydantic import BaseModel, Field

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
