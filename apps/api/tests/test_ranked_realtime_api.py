import asyncio
import json
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bukvogon.api.race_routes import router as race_router
from bukvogon.domain.anti_cheat import AntiCheatDecision, VerificationStatus
from bukvogon.services.anti_cheat import AcceptedRankedProgress
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


@dataclass(frozen=True)
class FakeChallenge:
    challenge_id: str
    nonce: str
    race_id: str
    player_id: str
    target_text: str


class FakeRankedAntiCheat:
    def __init__(self):
        self.challenges = {}
        self.batches = []
        self.verified = []

    async def issue_challenge(self, race_id, player_id, *, target_text):
        challenge = FakeChallenge(
            challenge_id=f'challenge-{player_id}',
            nonce=f'nonce-{player_id}',
            race_id=race_id,
            player_id=player_id,
            target_text=target_text,
        )
        self.challenges[challenge.challenge_id] = challenge
        return challenge

    async def accept_batch(self, race_id, player_id, batch):
        challenge = self.challenges[batch.challenge_id]
        if challenge.race_id != race_id or challenge.player_id != player_id or challenge.nonce != batch.nonce:
            raise ValueError('challenge binding mismatch')
        self.batches.append(batch)
        attempts = batch.offset + batch.errors
        return AcceptedRankedProgress(
            offset=batch.offset,
            cpm=420,
            accuracy=(1.0 if attempts == 0 else batch.offset / attempts),
        )

    async def verify_finish(self, challenge_id):
        self.verified.append(challenge_id)
        return AntiCheatDecision(
            status=VerificationStatus.VERIFIED,
            risk_score=4,
            reasons=(),
            hard_invalid=False,
            telemetry_coverage=1.0,
        )


def _app():
    app = FastAPI()
    service = RaceService(store=InMemoryRaceStore())
    anti_cheat = FakeRankedAntiCheat()
    app.state.race_service = service
    app.state.race_hub = RaceRealtimeHub(QueueBroker())
    app.state.ranked_anti_cheat = anti_cheat
    app.include_router(race_router, prefix='/v1')
    return app, anti_cheat


def test_ranked_race_uses_server_text_and_only_reveals_it_in_player_challenge():
    app, anti_cheat = _app()

    with TestClient(app) as client:
        response = client.post('/v1/ranked/races', json={'player_ids': ['a', 'b']})
        assert response.status_code == 201
        race = response.json()
        assert race['mode'] == 'ranked'
        assert race['text_length'] > 0
        assert 'target_text' not in race

        challenge_response = client.post(f"/v1/ranked/races/{race['race_id']}/challenge/a")
        assert challenge_response.status_code == 201
        challenge = challenge_response.json()
        assert challenge['type'] == 'ranked_challenge'
        assert challenge['challenge_id'] == 'challenge-a'
        assert challenge['nonce'] == 'nonce-a'
        assert len(challenge['target_text']) == race['text_length']
        assert anti_cheat.challenges['challenge-a'].target_text == challenge['target_text']

        intruder = client.post(f"/v1/ranked/races/{race['race_id']}/challenge/intruder")
        assert intruder.status_code == 403


def test_ranked_websocket_moves_racer_from_server_validated_batch_and_verifies_finish():
    app, anti_cheat = _app()

    with TestClient(app) as client:
        race = client.post('/v1/ranked/races', json={'player_ids': ['a']}).json()
        challenge = client.post(f"/v1/ranked/races/{race['race_id']}/challenge/a").json()
        target = challenge['target_text']

        with client.websocket_connect(
            f"/v1/ranked/races/{race['race_id']}/ws/a/{challenge['challenge_id']}"
        ) as socket:
            initial = socket.receive_json()
            assert initial['type'] == 'snapshot'

            socket.send_text(json.dumps({
                'type': 'ranked_telemetry',
                'challenge_id': challenge['challenge_id'],
                'nonce': challenge['nonce'],
                'batch_seq': 1,
                'offset': len(target),
                'fragment_start': 0,
                'fragment': target,
                'errors': 0,
                'corrections': 0,
                'focused': True,
                'visible': True,
                'events': [
                    {'dt_ms': 90 + (index % 5), 'kind': 'insert', 'trusted': True, 'delta': 1}
                    for index in range(len(target))
                ],
            }, ensure_ascii=False))

            updated = socket.receive_json()
            assert updated['type'] == 'snapshot'
            assert updated['racers'][0]['offset'] == len(target)

            verification = socket.receive_json()
            assert verification == {
                'type': 'verification',
                'status': 'verified',
                'risk_score': 4,
            }

        assert anti_cheat.verified == [challenge['challenge_id']]
