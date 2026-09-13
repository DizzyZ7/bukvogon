import pytest

from bukvogon.domain.typing import (
    TypingMode,
    calculate_metrics,
    normalize_character,
    validate_typed_prefix,
)


def test_casual_normalizes_yo_to_e():
    assert normalize_character("ё", TypingMode.CASUAL) == "е"
    assert normalize_character("Ё", TypingMode.CASUAL) == "Е"


def test_ranked_keeps_yo_distinct():
    assert normalize_character("ё", TypingMode.RANKED) == "ё"
    assert normalize_character("е", TypingMode.RANKED) == "е"


def test_casual_prefix_accepts_e_instead_of_yo():
    result = validate_typed_prefix("ёлка", "ел", TypingMode.CASUAL)
    assert result.valid is True
    assert result.matched_characters == 2
    assert result.error_index is None


def test_ranked_prefix_rejects_e_instead_of_yo():
    result = validate_typed_prefix("ёлка", "ел", TypingMode.RANKED)
    assert result.valid is False
    assert result.matched_characters == 0
    assert result.error_index == 0


def test_prefix_rejects_typing_beyond_target():
    result = validate_typed_prefix("кот", "коты", TypingMode.CASUAL)
    assert result.valid is False
    assert result.matched_characters == 3
    assert result.error_index == 3


def test_metrics_use_characters_as_primary_measure():
    metrics = calculate_metrics(correct_characters=250, total_keystrokes=300, elapsed_seconds=60)
    assert metrics.cpm == pytest.approx(250.0)
    assert metrics.wpm == pytest.approx(50.0)
    assert metrics.accuracy == pytest.approx(83.333333, rel=1e-5)


def test_metrics_reject_non_positive_elapsed_time():
    with pytest.raises(ValueError):
        calculate_metrics(correct_characters=10, total_keystrokes=10, elapsed_seconds=0)
