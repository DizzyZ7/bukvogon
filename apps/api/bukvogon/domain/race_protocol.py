from __future__ import annotations

from dataclasses import dataclass
import json
import math

MAX_WS_MESSAGE_BYTES = 2048
MIN_PROGRESS_INTERVAL_SECONDS = 0.08


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    offset: int
    cpm: int
    accuracy: float


def parse_progress_event(raw: str) -> ProgressEvent:
    if not isinstance(raw, str):
        raise ValueError('message must be text')
    if len(raw.encode('utf-8')) > MAX_WS_MESSAGE_BYTES:
        raise ValueError('message too large')

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError('invalid json') from exc

    if not isinstance(payload, dict):
        raise ValueError('invalid progress event')

    expected_fields = {'type', 'offset', 'cpm', 'accuracy'}
    if set(payload) != expected_fields or payload.get('type') != 'progress':
        raise ValueError('invalid progress event')

    offset = payload.get('offset')
    cpm = payload.get('cpm')
    accuracy = payload.get('accuracy')

    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError('offset must be a non-negative integer')
    if isinstance(cpm, bool) or not isinstance(cpm, int) or cpm < 0:
        raise ValueError('cpm must be a non-negative integer')
    if isinstance(accuracy, bool) or not isinstance(accuracy, (int, float)):
        raise ValueError('accuracy must be numeric')

    normalized_accuracy = float(accuracy)
    if not math.isfinite(normalized_accuracy) or not 0 <= normalized_accuracy <= 1:
        raise ValueError('accuracy must be between 0 and 1')

    return ProgressEvent(
        offset=offset,
        cpm=cpm,
        accuracy=normalized_accuracy,
    )
