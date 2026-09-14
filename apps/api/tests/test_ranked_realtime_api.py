import asyncio
import json
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bukvogon.api.race_routes import router as race_router
from bukvogon.domain.anti_cheat import AntiCheatDecision, VerificationStatus
from bukvogon.domain.auth import AuthenticatedPrincipal
from bukvogon.domain.entitlements import Entitlement, EntitlementStatus
from bukvogon.services.anti_cheat import AcceptedRankedProgress
from bukvogon.services.auth import AuthenticationError
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


@dataclass(frozen=True)
class FakeTicketGrant:
    ticket: str
    expires_in_seconds: int = 30


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


class FakeAuthService:
    def __init__(self):
        pro = Entitlement(EntitlementStatus.PRO_ACTIVE)
        free = Entitlement(EntitlementStatus.FREE)
        self.principals = {
            'pro-a': AuthenticatedPrincipal('a', pro),
            'pro-b': AuthenticatedPrincipal('b', pro),
            'pro-c': AuthenticatedPrincipal('c', pro),
            'free-user': AuthenticatedPrincipal('free-user', free),
        }

    async def resolve_access_token(self, token):
        principal = self.principals.get(token)
        if principal is None:
            raise AuthenticationError('invalid session')
        return principal


class FakeAuthRepository:
    def __init__(self):
        self.entitlements = {
            'a': Entitlement(EntitlementStatus.PRO_ACTIVE),
            'b': Entitlement(EntitlementStatus.PRO_ACTIVE),
            'c': Entitlement(EntitlementStatus.PRO_ACTIVE),
            'free-user': Entitlement(EntitlementStatus.FREE),
        }

    async def get_entitlements(self, user_ids):
        return {
            user_id: self.entitlements[user_id]
            for user_id in user_ids
            if user_id in self.entitlements
        }


class FakeWsTicketStore:
    def __init__(self):
        self.bindings = {}
        self.consumed = []

    async def issue(self, user_id, race_id, challenge_id):
        ticket = f'ticket-{user_id}-{challenge_id}'
        self.bindings[ticket] = (user_id, race_id, challenge_id)
        return FakeTicketGrant(ticket=ticket)

    async def consume(self, ticket, *, race_id, challenge_id):
        binding = self.bindings.get(ticket)
        if binding is None:
            raise ValueError('ticket expired or consumed')
        user_id, bound_race_id, bound_challenge_id = binding
        if bound_race_id != race_id or bound_challenge_id != challenge_id:
            raise ValueError('ticket binding mismatch')
        del self.bindings[ticket]
        self.consumed.append(ticket)
        return user_id


def _auth(token):
    return {'Authorization': f'Bearer {token}'}


def _app():
    app = FastAPI()
    service = RaceService(store=InMemoryRaceStore())
    anti_cheat = FakeRankedAntiCheat()
    tickets = FakeWsTicketStore()
    app.state.race_service = service
    app.state.race_hub = RaceRealtimeHub(QueueBroker())
    app.state.ranked_anti_cheat = anti_cheat
    app.state.auth_service = FakeAuthService()
    app.state.auth_repository = FakeAuthRepository()
    app.state.ws_ticket_store = tickets
    app.include_router(race_router, prefix='/v1')
    return app, anti_cheat, tickets


def test_ranked_creation_requires_pro_and_validates_every_participant_server_side():
    app, _, _ = _app()

    with TestClient(app) as client:
        assert client.post('/v1/ranked/races', json={'player_ids': ['a', 'b']}).status_code == 401
        assert client.post(
            '/v1/ranked/races',
            json={'player_ids': ['free-user']},
            headers=_auth('free-user'),
        ).status_code == 403
        assert client.post(
            '/v1/ranked/races',
            json={'player_ids': ['a', 'b']},
            headers=_auth('pro-c'),
        ).status_code == 403
        assert client.post(
            '/v1/ranked/races',
            json={'player_ids': ['a', 'free-user']},
            headers=_auth('pro-a'),
        ).status_code == 422

        allowed = client.post(
            '/v1/ranked/races',
            json={'player_ids': ['a', 'b']},
            headers=_auth('pro-a'),
        )
        assert allowed.status_code == 201
        assert allowed.json()['mode'] == 'ranked'


def test_ranked_challenge_derives_player_from_bearer_and_returns_one_time_ws_ticket():
    app, anti_cheat, tickets = _app()

    with TestClient(app) as client:
        race = client.post(
            '/v1/ranked/races',
            json={'player_ids': ['a', 'b']},
            headers=_auth('pro-a'),
        ).json()
        assert 'target_text' not in race

        challenge_response = client.post(
            f"/v1/ranked/races/{race['race_id']}/challenge",
            headers=_auth('pro-a'),
        )
        assert challenge_response.status_code == 201
        challenge = challenge_response.json()
        assert challenge['type'] == 'ranked_challenge'
        assert challenge['challenge_id'] == 'challenge-a'
        assert challenge['nonce'] == 'nonce-a'
        assert challenge['ws_ticket'].startswith('ticket-a-')
        assert challenge['ws_ticket_expires_in_seconds'] == 30
        assert anti_cheat.challenges['challenge-a'].player_id == 'a'
        assert tickets.bindings[challenge['ws_ticket']][0] == 'a'

        intruder = client.post(
            f"/v1/ranked/races/{race['race_id']}/challenge",
            headers=_auth('pro-c'),
        )
        assert intruder.status_code == 403

        old_spoofable_route = client.post(
            f"/v1/ranked/races/{race['race_id']}/challenge/a",
            headers=_auth('pro-c'),
        )
        assert old_spoofable_route.status_code == 404


def test_ranked_websocket_uses_ticket_owned_identity_and_ticket_cannot_replay():
    app, anti_cheat, tickets = _app()

    with TestClient(app) as client:
        race = client.post(
            '/v1/ranked/races',
            json={'player_ids': ['a']},
            headers=_auth('pro-a'),
        ).json()
        challenge = client.post(
            f"/v1/ranked/races/{race['race_id']}/challenge",
            headers=_auth('pro-a'),
        ).json()
        target = challenge['target_text']
        ticket = challenge['ws_ticket']

        with client.websocket_connect(
            f"/v1/ranked/races/{race['race_id']}/ws/{challenge['challenge_id']}?ticket={ticket}"
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
        assert tickets.consumed == [ticket]

        try:
            with client.websocket_connect(
                f"/v1/ranked/races/{race['race_id']}/ws/{challenge['challenge_id']}?ticket={ticket}"
            ):
                raise AssertionError('replayed ticket unexpectedly connected')
        except Exception:
            pass
