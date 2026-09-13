from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Protocol

from bukvogon.domain.race_session import RacePlayerState, RaceSession


@dataclass(frozen=True, slots=True)
class PersistedRaceResult:
    race_id: str
    player_id: str
    place: int
    cpm: int
    accuracy: float


class RaceStore(Protocol):
    async def create(self, race: RaceSession) -> None: ...
    async def get(self, race_id: str) -> RaceSession | None: ...
    async def save(self, race: RaceSession) -> None: ...


class InMemoryRaceStore:
    def __init__(self) -> None:
        self._races: dict[str, RaceSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, race_id: str) -> asyncio.Lock:
        return self._locks.setdefault(race_id, asyncio.Lock())

    async def create(self, race: RaceSession) -> None:
        async with self.lock_for(race.race_id):
            if race.race_id in self._races:
                raise ValueError('race already exists')
            self._races[race.race_id] = RaceSession.from_dict(race.to_dict())

    async def get(self, race_id: str) -> RaceSession | None:
        race = self._races.get(race_id)
        return None if race is None else RaceSession.from_dict(race.to_dict())

    async def save(self, race: RaceSession) -> None:
        async with self.lock_for(race.race_id):
            if race.race_id not in self._races:
                raise ValueError('race does not exist')
            self._races[race.race_id] = RaceSession.from_dict(race.to_dict())


PersistResult = Callable[[PersistedRaceResult], Awaitable[None]]


async def _noop_persist_result(_: PersistedRaceResult) -> None:
    return None


class RaceService:
    def __init__(
        self,
        *,
        store: RaceStore,
        persist_result: PersistResult = _noop_persist_result,
    ) -> None:
        self._store = store
        self._persist_result = persist_result
        self._locks: dict[str, asyncio.Lock] = {}

    def _lock_for(self, race_id: str) -> asyncio.Lock:
        return self._locks.setdefault(race_id, asyncio.Lock())

    async def create_race(
        self,
        race_id: str,
        *,
        text_length: int,
        player_ids: list[str] | tuple[str, ...],
    ) -> RaceSession:
        race = RaceSession.create(race_id, text_length=text_length, player_ids=player_ids)
        await self._store.create(race)
        return race

    async def get_race(self, race_id: str) -> RaceSession:
        race = await self._store.get(race_id)
        if race is None:
            raise ValueError('race not found')
        return race

    async def get_snapshot(self, race_id: str) -> dict[str, object]:
        return (await self.get_race(race_id)).snapshot()

    async def apply_progress(
        self,
        race_id: str,
        player_id: str,
        *,
        offset: int,
        cpm: int,
        accuracy: float,
    ) -> RacePlayerState:
        async with self._lock_for(race_id):
            race = await self.get_race(race_id)
            player = race.apply_progress(
                player_id,
                offset=offset,
                cpm=cpm,
                accuracy=accuracy,
            )
            await self._store.save(race)

            if player.place is not None:
                await self._persist_result(
                    PersistedRaceResult(
                        race_id=race.race_id,
                        player_id=player.player_id,
                        place=player.place,
                        cpm=player.cpm,
                        accuracy=player.accuracy,
                    )
                )

            return player
