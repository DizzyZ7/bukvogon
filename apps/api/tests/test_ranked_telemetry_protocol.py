import json

import pytest

from bukvogon.domain.race_protocol import parse_ranked_telemetry_batch


def _payload() -> dict[str, object]:
    return {
        'type': 'ranked_telemetry',
        'challenge_id': 'challenge-1',
        'nonce': 'nonce-0123456789abcdef',
        'batch_seq': 1,
        'offset': 3,
        'fragment_start': 0,
        'fragment': 'кот',
        'errors': 0,
        'corrections': 0,
        'focused': True,
        'visible': True,
        'events': [
            {'dt_ms': 90, 'kind': 'insert', 'trusted': True, 'delta': 1, 'input_type': 'insertText'},
            {'dt_ms': 80, 'kind': 'insert', 'trusted': True, 'delta': 1, 'input_type': 'insertText'},
            {'dt_ms': 110, 'kind': 'insert', 'trusted': True, 'delta': 1, 'input_type': 'insertText'},
        ],
    }


def test_parses_bounded_ranked_telemetry_batch():
    batch = parse_ranked_telemetry_batch(json.dumps(_payload(), ensure_ascii=False))

    assert batch.challenge_id == 'challenge-1'
    assert batch.batch_seq == 1
    assert batch.offset == 3
    assert batch.fragment == 'кот'
    assert len(batch.events) == 3
    assert batch.events[0].kind.value == 'insert'


def test_rejects_unknown_top_level_fields():
    payload = _payload()
    payload['admin'] = True

    with pytest.raises(ValueError, match='invalid ranked telemetry event'):
        parse_ranked_telemetry_batch(json.dumps(payload, ensure_ascii=False))


def test_rejects_more_than_16_events_per_batch():
    payload = _payload()
    payload['events'] = [
        {'dt_ms': 10, 'kind': 'insert', 'trusted': True, 'delta': 1}
        for _ in range(17)
    ]

    with pytest.raises(ValueError, match='too many telemetry events'):
        parse_ranked_telemetry_batch(json.dumps(payload, separators=(',', ':')))


def test_rejects_unknown_event_kind():
    payload = _payload()
    payload['events'][0]['kind'] = 'robot'

    with pytest.raises(ValueError, match='invalid telemetry kind'):
        parse_ranked_telemetry_batch(json.dumps(payload, ensure_ascii=False))


def test_rejects_out_of_bounds_event_delta():
    payload = _payload()
    payload['events'][0]['delta'] = 100

    with pytest.raises(ValueError, match='delta'):
        parse_ranked_telemetry_batch(json.dumps(payload, ensure_ascii=False))


def test_rejects_fragment_that_does_not_match_claimed_offset_range():
    payload = _payload()
    payload['fragment'] = 'ко'

    with pytest.raises(ValueError, match='fragment length'):
        parse_ranked_telemetry_batch(json.dumps(payload, ensure_ascii=False))


def test_rejects_non_positive_batch_sequence():
    payload = _payload()
    payload['batch_seq'] = 0

    with pytest.raises(ValueError, match='batch_seq'):
        parse_ranked_telemetry_batch(json.dumps(payload, ensure_ascii=False))
