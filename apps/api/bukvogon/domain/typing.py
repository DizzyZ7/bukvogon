from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class TypingMode(StrEnum):
    CASUAL = "casual"
    RANKED = "ranked"
    PRACTICE = "practice"


@dataclass(frozen=True, slots=True)
class PrefixValidation:
    valid: bool
    matched_characters: int
    error_index: int | None


@dataclass(frozen=True, slots=True)
class TypingMetrics:
    cpm: float
    wpm: float
    accuracy: float


def normalize_character(character: str, mode: TypingMode) -> str:
    if len(character) != 1:
        raise ValueError("normalize_character expects exactly one character")
    if mode in {TypingMode.CASUAL, TypingMode.PRACTICE}:
        return {"ё": "е", "Ё": "Е"}.get(character, character)
    return character


def validate_typed_prefix(target: str, typed: str, mode: TypingMode) -> PrefixValidation:
    comparable_length = min(len(target), len(typed))
    for index in range(comparable_length):
        expected = normalize_character(target[index], mode)
        actual = normalize_character(typed[index], mode)
        if expected != actual:
            return PrefixValidation(False, index, index)

    if len(typed) > len(target):
        return PrefixValidation(False, len(target), len(target))

    return PrefixValidation(True, len(typed), None)


def calculate_metrics(
    *,
    correct_characters: int,
    total_keystrokes: int,
    elapsed_seconds: float,
) -> TypingMetrics:
    if elapsed_seconds <= 0:
        raise ValueError("elapsed_seconds must be positive")
    if correct_characters < 0 or total_keystrokes < 0:
        raise ValueError("character counts cannot be negative")
    if correct_characters > total_keystrokes:
        raise ValueError("correct_characters cannot exceed total_keystrokes")

    minutes = elapsed_seconds / 60.0
    cpm = correct_characters / minutes
    wpm = cpm / 5.0
    accuracy = 100.0 if total_keystrokes == 0 else (correct_characters / total_keystrokes) * 100.0
    return TypingMetrics(cpm=cpm, wpm=wpm, accuracy=accuracy)
