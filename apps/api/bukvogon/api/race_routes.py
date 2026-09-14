from __future__ import annotations

import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, WebSocket, WebSocketDisconnect, status
from pydantic import BaseModel, Field

from bukvogon.api.auth import require_pro_principal
from bukvogon.domain.auth import AuthenticatedPrincipal
from bukvogon.domain.entitlements import can_play_ranked
from bukvogon.domain.race_protocol import (
    MIN_PROGRESS_INTERVAL_SECONDS,
    parse_progress_event,
    parse_ranked_telemetry_batch,
)
from bukvogon.domain.text_catalog import choose_ranked_text
from bukvogon.infrastructure.redis_ws_tickets import RedisWsTicketStore
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


def _ws_ticket_store_from_request(request: Request) -> RedisWsTicketStore:
    return request.app.state.ws_ticket_store


def _ws_ticket_store_from_websocket(websocket: WebSocket) -> RedisWsTicketStore:
    return websocket.app.state.ws_ticket_store


def _auth_repository_from_request(request: Request):
    return request.app.state.auth_repository


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
async def create_ranked_race(
    payload: CreateRankedRaceRequest,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_pro_principal),
) -> dict[str, object]:
    player_ids = list(dict.fromkeys(payload.player_ids))
    if len(player_ids) != len(payload.player_ids):
        raise HTTPException(status_code=422, detail='ranked player ids must be unique')
    if principal.user_id not in player_ids:
        raise HTTPException(status_code=403, detail='authenticated player is not part of requested race')

    auth_repository = _auth_repository_from_request(request)
    entitlements = await auth_repository.get_entitlements(player_ids)
    if set(entitlements) != set(player_ids) or any(
        not can_play_ranked(entitlements[player_id])
        for player_id in player_ids
    ):
        raise HTTPException(status_code=422, detail='all ranked participants must have active pro')

    service = _service_from_request(request)
    target_text = choose_ranked_text()
    race_id = uuid4().hex
    try:
        race = await service.create_race(
            race_id,
            text_length=len(target_text),
            player_ids=player_ids,
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


@router.post('/ranked/races/{race_id}/challenge', status_code=status.HTTP_201_CREATED)
async def issue_ranked_challenge(
    race_id: str,
    request: Request,
    principal: AuthenticatedPrincipal = Depends(require_pro_principal),
) -> dict[str, object]:
    service = _service_from_request(request)
    anti_cheat = _anti_cheat_from_request(request)
    player_id = principal.user_id
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
    ws_ticket = await _ws_ticket_store_from_request(request).issue(
        player_id,
        race_id,
        challenge.challenge_id,
    )
    return {
        'type': 'ranked_challenge',
        'challenge_id': challenge.challenge_id,
        'nonce': challenge.nonce,
        'target_text': challenge.target_text,
        'ws_ticket': ws_ticket.ticket,
        'ws_ticket_expires_in_seconds': ws_ticket.expires_in_seconds,
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


@router.websocket('/ranked/races/{race_id}/ws/{challenge_id}')
async def ranked_race_websocket(
    websocket: WebSocket,
    race_id: str,
    challenge_id: str,
    ticket: str | None = None,
) -> None:
    service = _service_from_websocket(websocket)
    hub = _hub_from_websocket(websocket)
    anti_cheat = _anti_cheat_from_websocket(websocket)
    ticket_store = _ws_ticket_store_from_websocket(websocket)
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
        if not ticket:
            await websocket.close(code=1008, reason='websocket ticket required')
            return

        try:
            player_id = await ticket_store.consume(
                ticket,
                race_id=race_id,
                challenge_id=challenge_id,
            )
        except ValueError:
            await websocket.close(code=1008, reason='invalid websocket ticket')
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
