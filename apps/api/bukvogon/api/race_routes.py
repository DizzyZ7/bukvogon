from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from bukvogon.domain.race_protocol import (
    MIN_PROGRESS_INTERVAL_SECONDS,
    parse_progress_event,
    parse_ranked_telemetry_batch,
)
from bukvogon.domain.text_catalog import choose_ranked_text
from bukvogon.services.anti_cheat import RankedAntiCheatService
from bukvogon.services.races import RaceService
from bukvogon.services.realtime import RaceRealtimeHub

router = APIRouter(tags=['races'])


class CreateRaceRequest(BaseModel):
    text_length: int = Field(ge=1, le=20_000)
    player_ids: list[str] = Field(min_length=1, max_length=6)


class CreateRankedRaceRequest(BaseModel):
    player_ids: list[str] = Field(min_length=1, max_length=6)


def _service_from_request(request: Request) -> RaceService:
    return request.app.state.race_service


def _service_from_websocket(websocket: WebSocket) -> RaceService:
    return websocket.app.state.race_service


def _hub_from_websocket(websocket: WebSocket) -> RaceRealtimeHub:
    return websocket.app.state.race_hub


def _anti_cheat_from_request(request: Request) -> RankedAntiCheatService:
    return request.app.state.ranked_anti_cheat


def _anti_cheat_from_websocket(websocket: WebSocket) -> RankedAntiCheatService:
    return websocket.app.state.ranked_anti_cheat


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


@router.post('/ranked/races', status_code=status.HTTP_201_CREATED)
async def create_ranked_race(payload: CreateRankedRaceRequest, request: Request) -> dict[str, object]:
    service = _service_from_request(request)
    target_text = choose_ranked_text()
    race_id = uuid4().hex
    try:
        race = await service.create_race(
            race_id,
            text_length=len(target_text),
            player_ids=payload.player_ids,
            ranked=True,
            target_text=target_text,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {'mode': 'ranked', **race.snapshot()}


@router.get('/races/{race_id}')
async def get_race(race_id: str, request: Request) -> dict[str, object]:
    service = _service_from_request(request)
    try:
        return await service.get_snapshot(race_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail='race not found') from exc


@router.post('/ranked/races/{race_id}/challenge/{player_id}', status_code=status.HTTP_201_CREATED)
async def issue_ranked_challenge(race_id: str, player_id: str, request: Request) -> dict[str, object]:
    service = _service_from_request(request)
    anti_cheat = _anti_cheat_from_request(request)
    try:
        race = await service.get_race(race_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail='race not found') from exc

    if not race.ranked or race.target_text is None:
        raise HTTPException(status_code=404, detail='ranked race not found')
    if player_id not in race.players:
        raise HTTPException(status_code=403, detail='player is not part of race')

    challenge = await anti_cheat.issue_challenge(
        race_id,
        player_id,
        target_text=race.target_text,
    )
    return {
        'type': 'ranked_challenge',
        'challenge_id': challenge.challenge_id,
        'nonce': challenge.nonce,
        'target_text': challenge.target_text,
    }


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


@router.websocket('/ranked/races/{race_id}/ws/{player_id}/{challenge_id}')
async def ranked_race_websocket(
    websocket: WebSocket,
    race_id: str,
    player_id: str,
    challenge_id: str,
) -> None:
    service = _service_from_websocket(websocket)
    hub = _hub_from_websocket(websocket)
    anti_cheat = _anti_cheat_from_websocket(websocket)
    joined = False

    try:
        try:
            race = await service.get_race(race_id)
        except ValueError:
            await websocket.close(code=1008, reason='race not found')
            return

        if not race.ranked or race.target_text is None:
            await websocket.close(code=1008, reason='ranked race not found')
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
                batch = parse_ranked_telemetry_batch(raw)
                if batch.challenge_id != challenge_id:
                    raise ValueError('challenge id does not match websocket')
                progress = await anti_cheat.accept_batch(race_id, player_id, batch)
                player = await service.apply_progress(
                    race_id,
                    player_id,
                    offset=progress.offset,
                    cpm=progress.cpm,
                    accuracy=progress.accuracy,
                )
            except ValueError as exc:
                await websocket.send_json({'type': 'error', 'detail': str(exc)})
                continue

            last_accepted_at = now
            snapshot_message = _snapshot_message(await service.get_snapshot(race_id))

            if player.place is not None:
                # The finisher gets its authoritative final position before any
                # verification status. Remove it from local fan-out first so the
                # same final snapshot is not echoed back a second time.
                await websocket.send_json(snapshot_message)
                await hub.remove(race_id, websocket)
                joined = False
                await hub.publish(race_id, snapshot_message)

                decision = await anti_cheat.verify_finish(challenge_id)
                await websocket.send_json({
                    'type': 'verification',
                    'status': decision.status.value,
                    'risk_score': decision.risk_score,
                })
                return

            await hub.publish(race_id, snapshot_message)

    except WebSocketDisconnect:
        return
    finally:
        if joined:
            await hub.remove(race_id, websocket)
