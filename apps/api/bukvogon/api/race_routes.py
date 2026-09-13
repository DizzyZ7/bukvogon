from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from bukvogon.domain.race_protocol import MIN_PROGRESS_INTERVAL_SECONDS, parse_progress_event
from bukvogon.services.races import RaceService
from bukvogon.services.realtime import RaceRealtimeHub

router = APIRouter(tags=['races'])


class CreateRaceRequest(BaseModel):
    text_length: int = Field(ge=1, le=20_000)
    player_ids: list[str] = Field(min_length=1, max_length=6)


def _service_from_request(request: Request) -> RaceService:
    return request.app.state.race_service


def _service_from_websocket(websocket: WebSocket) -> RaceService:
    return websocket.app.state.race_service


def _hub_from_websocket(websocket: WebSocket) -> RaceRealtimeHub:
    return websocket.app.state.race_hub


def _snapshot_message(snapshot: dict[str, object]) -> dict[str, object]:
    return {'type': 'snapshot', **snapshot}


@router.post('/races', status_code=status.HTTP_201_CREATED)
async def create_race(payload: CreateRaceRequest, request: Request) -> dict[str, object]:
    service = _service_from_request(request)
    race_id = uuid4().hex
    try:
        race = await service.create_race(
            race_id,
            text_length=payload.text_length,
            player_ids=payload.player_ids,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return race.snapshot()


@router.get('/races/{race_id}')
async def get_race(race_id: str, request: Request) -> dict[str, object]:
    service = _service_from_request(request)
    try:
        return await service.get_snapshot(race_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail='race not found') from exc


@router.websocket('/races/{race_id}/ws/{player_id}')
async def race_websocket(websocket: WebSocket, race_id: str, player_id: str) -> None:
    service = _service_from_websocket(websocket)
    hub = _hub_from_websocket(websocket)
    joined = False

    try:
        try:
            race = await service.get_race(race_id)
        except ValueError:
            await websocket.close(code=1008, reason='race not found')
            return

        if player_id not in race.players:
            await websocket.close(code=1008, reason='player is not part of race')
            return

        await websocket.accept()
        await hub.add(race_id, websocket)
        joined = True
        await websocket.send_json(_snapshot_message(race.snapshot()))

        last_accepted_at = 0.0
        while True:
            raw = await websocket.receive_text()
            now = time.monotonic()
            if last_accepted_at and now - last_accepted_at < MIN_PROGRESS_INTERVAL_SECONDS:
                continue

            try:
                event = parse_progress_event(raw)
                await service.apply_progress(
                    race_id,
                    player_id,
                    offset=event.offset,
                    cpm=event.cpm,
                    accuracy=event.accuracy,
                )
            except ValueError as exc:
                await websocket.send_json({'type': 'error', 'detail': str(exc)})
                continue

            last_accepted_at = now
            snapshot = await service.get_snapshot(race_id)
            await hub.publish(race_id, _snapshot_message(snapshot))

    except WebSocketDisconnect:
        return
    finally:
        if joined:
            await hub.remove(race_id, websocket)
