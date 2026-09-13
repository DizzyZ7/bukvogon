import asyncio
import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bukvogon.api.race_routes import router as race_router
from bukvogon.services.races import InMemoryRaceStore, RaceService
from bukvogon.services.realtime import RaceRealtimeHub


class QueueBroker:
    def __init__(self):
        self.queues = {}

    async def publish(self, race_id, snapshot):
        await self.queues.setdefault(race_id, asyncio.Queue()).put(snapshot)

    async def listen(self, race_id):
        queue = self.queues.setdefault(race_id, asyncio.Queue())
        while True:
            yield await queue.get()


def test_realtime_race_create_snapshot_and_websocket_progress():
    app = FastAPI()
    service = RaceService(store=InMemoryRaceStore())
    hub = RaceRealtimeHub(QueueBroker())
    app.state.race_service = service
    app.state.race_hub = hub
    app.include_router(race_router, prefix='/v1')

    with TestClient(app) as client:
        response = client.post('/v1/races', json={
            'text_length': 10,
            'player_ids': ['a', 'b'],
        })
        assert response.status_code == 201
        created = response.json()
        race_id = created['race_id']
        assert created['text_length'] == 10

        snapshot = client.get(f'/v1/races/{race_id}')
        assert snapshot.status_code == 200
        assert snapshot.json()['race_id'] == race_id

        with client.websocket_connect(f'/v1/races/{race_id}/ws/a') as socket:
            initial = socket.receive_json()
            assert initial['type'] == 'snapshot'
            assert initial['race_id'] == race_id

            socket.send_text(json.dumps({
                'type': 'progress',
                'offset': 5,
                'cpm': 320,
                'accuracy': 0.96,
            }))
            updated = socket.receive_json()
            assert updated['type'] == 'snapshot'
            racer = next(item for item in updated['racers'] if item['player_id'] == 'a')
            assert racer['offset'] == 5


def test_realtime_websocket_rejects_player_outside_race():
    app = FastAPI()
    service = RaceService(store=InMemoryRaceStore())
    hub = RaceRealtimeHub(QueueBroker())
    app.state.race_service = service
    app.state.race_hub = hub
    app.include_router(race_router, prefix='/v1')

    with TestClient(app) as client:
        created = client.post('/v1/races', json={
            'text_length': 10,
            'player_ids': ['a'],
        }).json()

        try:
            with client.websocket_connect(f"/v1/races/{created['race_id']}/ws/intruder"):
                raise AssertionError('websocket should have been rejected')
        except Exception as exc:
            assert '1008' in str(exc) or exc.__class__.__name__ in {'WebSocketDisconnect', 'WebSocketDenialResponse'}
