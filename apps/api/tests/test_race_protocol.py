import json

import pytest

from bukvogon.domain.race_protocol import (
    MAX_WS_MESSAGE_BYTES,
    MIN_PROGRESS_INTERVAL_SECONDS,
    ProgressEvent,
    parse_progress_event,
)


def test_protocol_limits_keep_updates_compact_and_bounded():
    assert MAX_WS_MESSAGE_BYTES == 2048
    assert MIN_PROGRESS_INTERVAL_SECONDS >= 0.08


def test_progress_event_accepts_compact_valid_payload():
    raw = json.dumps({
        'type': 'progress',
        'offset': 42,
        'cpm': 350,
        'accuracy': 0.97,
    })

    event = parse_progress_event(raw)

    assert event == ProgressEvent(offset=42, cpm=350, accuracy=0.97)


def test_progress_event_rejects_wrong_type_and_extra_fields():
    with pytest.raises(ValueError):
        parse_progress_event(json.dumps({
            'type': 'finish',
            'offset': 42,
            'cpm': 350,
            'accuracy': 0.97,
        }))

    with pytest.raises(ValueError):
        parse_progress_event(json.dumps({
            'type': 'progress',
            'offset': 42,
            'cpm': 350,
            'accuracy': 0.97,
            'raw_keys': 'do not accept this',
        }))


def test_progress_event_rejects_oversized_messages():
    oversized = '{"type":"progress","padding":"' + ('x' * MAX_WS_MESSAGE_BYTES) + '"}'
    with pytest.raises(ValueError, match='too large'):
        parse_progress_event(oversized)
