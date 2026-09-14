import pytest

from bukvogon.domain.race_session import RaceSession


def test_ranked_race_keeps_target_internal_and_serializable_but_hides_it_from_snapshot():
    race = RaceSession.create(
        'ranked-1',
        text_length=5,
        player_ids=['a', 'b'],
        ranked=True,
        target_text='котик',
    )

    assert race.ranked is True
    assert race.target_text == 'котик'
    assert 'target_text' not in race.snapshot()

    restored = RaceSession.from_dict(race.to_dict())
    assert restored.ranked is True
    assert restored.target_text == 'котик'


def test_ranked_race_requires_server_target_matching_text_length():
    with pytest.raises(ValueError, match='ranked race requires target text'):
        RaceSession.create('ranked-1', text_length=5, player_ids=['a'], ranked=True)

    with pytest.raises(ValueError, match='target text length'):
        RaceSession.create(
            'ranked-1',
            text_length=5,
            player_ids=['a'],
            ranked=True,
            target_text='кот',
        )
