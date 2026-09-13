import asyncio
from contextlib import asynccontextmanager

import pytest

from bukvogon.domain.race_session import (
    MAX_RACE_PLAYERS,
    RACE_TTL_SECONDS,
    RaceSession,
    RaceStatus,
)
from bukvogon.services.races import InMemoryRaceStore, RaceService


def test_race_session_has_bounded_capacity_and_twenty_minute_ttl():
    assert MAX_RACE_PLAYERS == 6
    assert RACE_TTL_SECONDS == 20 * 60

    race = RaceSession.create('race-1', text_length=200, player_ids=['a', 'b'])

    assert race.status is RaceStatus.RUNNING
    assert list(race.players) == ['a', 'b']


def test_race_rejects_too_many_players():
    with pytest.raises(ValueError, match='at most 6 players'):
        RaceSession.create(
            'race-1',
            text_length=200,
            player_ids=[str(index) for index in range(MAX_RACE_PLAYERS + 1)],
        )


def test_progress_is_monotonic_and_bounded():
    race = RaceSession.create('race-1', text_length=100, player_ids=['a', 'b'])

    race.apply_progress('a', offset=30, cpm=300, accuracy=0.95)

    with pytest.raises(ValueError, match='cannot go backwards'):
        race.apply_progress('a', offset=29, cpm=301, accuracy=0.95)

    with pytest.raises(ValueError, match='text length'):
        race.apply_progress('a', offset=101, cpm=301, accuracy=0.95)


def test_finishing_assigns_places_once_and_completed_player_cannot_resume():
    race = RaceSession.create('race-1', text_length=50, player_ids=['a', 'b'])

    first = race.apply_progress('b', offset=50, cpm=410, accuracy=0.99)
    second = race.apply_progress('a', offset=50, cpm=390, accuracy=0.97)

    assert first.place == 1
    assert second.place == 2
    assert race.status is RaceStatus.FINISHED

    with pytest.raises(ValueError, match='already finished'):
        race.apply_progress('b', offset=50, cpm=420, accuracy=1.0)


def test_snapshot_orders_finished_then_progressing_players():
    race = RaceSession.create('race-1', text_length=100, player_ids=['a', 'b', 'c'])
    race.apply_progress('a', offset=100, cpm=500, accuracy=0.99)
    race.apply_progress('b', offset=65, cpm=350, accuracy=0.96)
    race.apply_progress('c', offset=80, cpm=370, accuracy=0.97)

    snapshot = race.snapshot()

    assert [player['player_id'] for player in snapshot['racers']] == ['a', 'c', 'b']
    assert snapshot['racers'][0]['place'] == 1


def test_service_persists_finish_without_database_writes_for_intermediate_progress():
    async def scenario():
        store = InMemoryRaceStore()
        persisted = []

        async def persist_result(result):
            persisted.append(result)

        service = RaceService(store=store, persist_result=persist_result)
        await service.create_race('race-1', text_length=10, player_ids=['a', 'b'])

        await service.apply_progress('race-1', 'a', offset=5, cpm=300, accuracy=0.9)
        assert persisted == []

        await service.apply_progress('race-1', 'a', offset=10, cpm=320, accuracy=0.92)
        assert len(persisted) == 1
        assert persisted[0].player_id == 'a'
        assert persisted[0].place == 1

    asyncio.run(scenario())


def test_service_uses_store_level_lock_for_mutations():
    class LockAwareStore(InMemoryRaceStore):
        def __init__(self):
            super().__init__()
            self.lock_entered = False

        @asynccontextmanager
        async def lock(self, race_id: str):
            self.lock_entered = True
            async with self.lock_for(race_id):
                yield

    async def scenario():
        store = LockAwareStore()
        service = RaceService(store=store)
        await service.create_race('race-lock', text_length=10, player_ids=['a'])
        await service.apply_progress('race-lock', 'a', offset=1, cpm=100, accuracy=1.0)
        assert store.lock_entered is True

    asyncio.run(scenario())


def test_finish_persistence_runs_after_race_lock_is_released():
    class LockAwareStore(InMemoryRaceStore):
        def __init__(self):
            super().__init__()
            self.lock_active = False

        @asynccontextmanager
        async def lock(self, race_id: str):
            async with self.lock_for(race_id):
                self.lock_active = True
                try:
                    yield
                finally:
                    self.lock_active = False

    async def scenario():
        store = LockAwareStore()
        observed_lock_states = []

        async def persist_result(_):
            observed_lock_states.append(store.lock_active)

        service = RaceService(store=store, persist_result=persist_result)
        await service.create_race('race-db', text_length=5, player_ids=['a'])
        await service.apply_progress('race-db', 'a', offset=5, cpm=300, accuracy=1.0)

        assert observed_lock_states == [False]

    asyncio.run(scenario())
