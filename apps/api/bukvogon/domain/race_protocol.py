from __future__ import annotations

from dataclasses import dataclass
import json
import math

from bukvogon.domain.anti_cheat import TelemetryEvent, TelemetryKind

MAX_WS_MESSAGE_BYTES = 2048
MIN_PROGRESS_INTERVAL_SECONDS = 0.08
MAX_TELEMETRY_EVENTS_PER_BATCH = 16
MAX_FRAGMENT_CHARACTERS = 256


@dataclass(frozen=True, slots=True)
class ProgressEvent:
    offset: int
    cpm: int
    accuracy: float


@dataclass(frozen=True, slots=True)
class RankedTelemetryBatch:
    challenge_id: str
    nonce: str
    batch_seq: int
    offset: int
    fragment_start: int
    fragment: str
    errors: int
    corrections: int
    focused: bool
    visible: bool
    events: tuple[TelemetryEvent, ...]


def _load_message(raw: str) -> object:
    if not isinstance(raw, str):
        raise ValueError('message must be text')
    if len(raw.encode('utf-8')) > MAX_WS_MESSAGE_BYTES:
        raise ValueError('message too large')
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError('invalid json') from exc


def parse_progress_event(raw: str) -> ProgressEvent:
    payload = _load_message(raw)
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

    return ProgressEvent(offset=offset, cpm=cpm, accuracy=normalized_accuracy)


def _require_short_string(payload: dict[str, object], field: str, *, maximum: int = 128) -> str:
    value = payload.get(field)
    if not isinstance(value, str) or not value or len(value) > maximum:
        raise ValueError(f'{field} must be a non-empty string')
    return value


def _require_non_negative_int(payload: dict[str, object], field: str) -> int:
    value = payload.get(field)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f'{field} must be a non-negative integer')
    return value


def _parse_telemetry_event(payload: object) -> TelemetryEvent:
    if not isinstance(payload, dict):
        raise ValueError('invalid telemetry event')
    allowed_fields = {'dt_ms', 'kind', 'trusted', 'delta', 'input_type'}
    required_fields = {'dt_ms', 'kind', 'trusted', 'delta'}
    if not required_fields.issubset(payload) or not set(payload).issubset(allowed_fields):
        raise ValueError('invalid telemetry event')

    dt_ms = payload.get('dt_ms')
    delta = payload.get('delta')
    trusted = payload.get('trusted')
    kind_raw = payload.get('kind')
    input_type = payload.get('input_type')

    if isinstance(dt_ms, bool) or not isinstance(dt_ms, int) or not 0 <= dt_ms <= 60_000:
        raise ValueError('dt_ms must be an integer between 0 and 60000')
    if isinstance(delta, bool) or not isinstance(delta, int) or not -32 <= delta <= 32:
        raise ValueError('delta must be an integer between -32 and 32')
    if not isinstance(trusted, bool):
        raise ValueError('trusted must be boolean')
    if not isinstance(kind_raw, str):
        raise ValueError('invalid telemetry kind')
    try:
        kind = TelemetryKind(kind_raw)
    except ValueError as exc:
        raise ValueError('invalid telemetry kind') from exc
    if input_type is not None and (not isinstance(input_type, str) or len(input_type) > 64):
        raise ValueError('input_type must be a short string')

    return TelemetryEvent(
        dt_ms=dt_ms,
        kind=kind,
        trusted=trusted,
        delta=delta,
        input_type=input_type,
    )


def parse_ranked_telemetry_batch(raw: str) -> RankedTelemetryBatch:
    payload = _load_message(raw)
    if not isinstance(payload, dict):
        raise ValueError('invalid ranked telemetry event')

    expected_fields = {
        'type',
        'challenge_id',
        'nonce',
        'batch_seq',
        'offset',
        'fragment_start',
        'fragment',
        'errors',
        'corrections',
        'focused',
        'visible',
        'events',
    }
    if set(payload) != expected_fields or payload.get('type') != 'ranked_telemetry':
        raise ValueError('invalid ranked telemetry event')

    challenge_id = _require_short_string(payload, 'challenge_id')
    nonce = _require_short_string(payload, 'nonce')
    batch_seq = _require_non_negative_int(payload, 'batch_seq')
    if batch_seq <= 0:
        raise ValueError('batch_seq must be positive')
    offset = _require_non_negative_int(payload, 'offset')
    fragment_start = _require_non_negative_int(payload, 'fragment_start')
    errors = _require_non_negative_int(payload, 'errors')
    corrections = _require_non_negative_int(payload, 'corrections')

    fragment = payload.get('fragment')
    focused = payload.get('focused')
    visible = payload.get('visible')
    event_payloads = payload.get('events')

    if not isinstance(fragment, str) or len(fragment) > MAX_FRAGMENT_CHARACTERS:
        raise ValueError('fragment must be a bounded string')
    if fragment_start > offset:
        raise ValueError('fragment_start cannot exceed offset')
    if len(fragment) != offset - fragment_start:
        raise ValueError('fragment length must match claimed offset range')
    if not isinstance(focused, bool) or not isinstance(visible, bool):
        raise ValueError('focused and visible must be boolean')
    if not isinstance(event_payloads, list):
        raise ValueError('events must be a list')
    if len(event_payloads) > MAX_TELEMETRY_EVENTS_PER_BATCH:
        raise ValueError('too many telemetry events')

    events = tuple(_parse_telemetry_event(event) for event in event_payloads)
    return RankedTelemetryBatch(
        challenge_id=challenge_id,
        nonce=nonce,
        batch_seq=batch_seq,
        offset=offset,
        fragment_start=fragment_start,
        fragment=fragment,
        errors=errors,
        corrections=corrections,
        focused=focused,
        visible=visible,
        events=events,
    )
