from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import math

MAX_RACE_PLAYERS = 6
RACE_TTL_SECONDS = 20 * 60


class RaceStatus(StrEnum):
    RUNNING = 'running'
    FINISHED = 'finished'


@dataclass(slots=True)
class RacePlayerState:
    player_id: str
    offset: int = 0
    cpm: int = 0
    accuracy: float = 1.0
    place: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            'player_id': self.player_id,
            'offset': self.offset,
            'cpm': self.cpm,
            'accuracy': self.accuracy,
            'place': self.place,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> 'RacePlayerState':
        return cls(
            player_id=str(payload['player_id']),
            offset=int(payload.get('offset', 0)),
            cpm=int(payload.get('cpm', 0)),
            accuracy=float(payload.get('accuracy', 1.0)),
            place=(None if payload.get('place') is None else int(payload['place'])),
        )


@dataclass(slots=True)
class RaceSession:
    race_id: str
    text_length: int
    players: dict[str, RacePlayerState] = field(default_factory=dict)
    status: RaceStatus = RaceStatus.RUNNING
    finish_counter: int = 0
    ranked: bool = False
    target_text: str | None = None

    @classmethod
    def create(
        cls,
        race_id: str,
        *,
        text_length: int,
        player_ids: list[str] | tuple[str, ...],
        ranked: bool = False,
        target_text: str | None = None,
    ) -> 'RaceSession':
        if text_length <= 0:
            raise ValueError('text length must be positive')
        if not player_ids:
            raise ValueError('race requires at least one player')
        if len(player_ids) > MAX_RACE_PLAYERS:
            raise ValueError(f'race supports at most {MAX_RACE_PLAYERS} players')
        if len(set(player_ids)) != len(player_ids):
            raise ValueError('player ids must be unique')
        if ranked and not target_text:
            raise ValueError('ranked race requires target text')
        if target_text is not None and len(target_text) != text_length:
            raise ValueError('target text length must match race text length')

        return cls(
            race_id=race_id,
            text_length=text_length,
            players={player_id: RacePlayerState(player_id=player_id) for player_id in player_ids},
            ranked=ranked,
            target_text=target_text,
        )

    def apply_progress(
        self,
        player_id: str,
        *,
        offset: int,
        cpm: int,
        accuracy: float,
    ) -> RacePlayerState:
        if player_id not in self.players:
            raise ValueError('player is not part of this race')

        player = self.players[player_id]
        if player.place is not None:
            raise ValueError('player already finished')
        if offset < player.offset:
            raise ValueError('progress cannot go backwards')
        if offset > self.text_length:
            raise ValueError('progress exceeds race text length')
        if cpm < 0:
            raise ValueError('cpm cannot be negative')
        if not math.isfinite(accuracy) or not 0 <= accuracy <= 1:
            raise ValueError('accuracy must be between 0 and 1')

        player.offset = offset
        player.cpm = cpm
        player.accuracy = accuracy

        if offset == self.text_length:
            self.finish_counter += 1
            player.place = self.finish_counter
            if all(item.place is not None for item in self.players.values()):
                self.status = RaceStatus.FINISHED

        return player

    def snapshot(self) -> dict[str, object]:
        def sort_key(player: RacePlayerState) -> tuple[int, int, int]:
            if player.place is not None:
                return (0, player.place, 0)
            return (1, 0, -player.offset)

        ordered = sorted(self.players.values(), key=sort_key)
        return {
            'race_id': self.race_id,
            'status': self.status.value,
            'text_length': self.text_length,
            'racers': [player.to_dict() for player in ordered],
        }

    def to_dict(self) -> dict[str, object]:
        return {
            'race_id': self.race_id,
            'text_length': self.text_length,
            'status': self.status.value,
            'finish_counter': self.finish_counter,
            'ranked': self.ranked,
            'target_text': self.target_text,
            'players': [player.to_dict() for player in self.players.values()],
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> 'RaceSession':
        player_payloads = payload.get('players', [])
        if not isinstance(player_payloads, list):
            raise ValueError('players must be a list')
        players = [RacePlayerState.from_dict(item) for item in player_payloads if isinstance(item, dict)]
        target_text_raw = payload.get('target_text')
        return cls(
            race_id=str(payload['race_id']),
            text_length=int(payload['text_length']),
            status=RaceStatus(str(payload.get('status', RaceStatus.RUNNING.value))),
            finish_counter=int(payload.get('finish_counter', 0)),
            ranked=bool(payload.get('ranked', False)),
            target_text=(None if target_text_raw is None else str(target_text_raw)),
            players={player.player_id: player for player in players},
        )
