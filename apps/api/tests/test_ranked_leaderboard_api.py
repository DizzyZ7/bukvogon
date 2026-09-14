from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from bukvogon.api.leaderboard import router as leaderboard_router
from bukvogon.domain.auth import AuthenticatedPrincipal
from bukvogon.domain.entitlements import Entitlement, EntitlementStatus
from bukvogon.domain.ranked import RankedLeaderboardEntry
from bukvogon.services.auth import AuthenticationError


class FakeAuthService:
    def __init__(self):
        self.tokens = {
            'free': AuthenticatedPrincipal('free-user', Entitlement(EntitlementStatus.FREE)),
            'grace': AuthenticatedPrincipal('grace-user', Entitlement(EntitlementStatus.PRO_GRACE)),
            'expired': AuthenticatedPrincipal(
                'expired-user',
                Entitlement(
                    EntitlementStatus.PRO_ACTIVE,
                    datetime(2020, 1, 1, tzinfo=timezone.utc),
                ),
            ),
            'pro': AuthenticatedPrincipal('pro-user', Entitlement(EntitlementStatus.PRO_ACTIVE)),
        }

    async def resolve_access_token(self, token: str):
        principal = self.tokens.get(token)
        if principal is None:
            raise AuthenticationError('invalid session')
        return principal


class FakeLeaderboardRepository:
    def __init__(self):
        self.limits = []

    async def fetch_ranked_leaderboard(self, *, limit: int):
        self.limits.append(limit)
        return [
            RankedLeaderboardEntry('alpha', 1420.0, 31, 1),
            RankedLeaderboardEntry('beta', 1390.5, 28, 1000),
        ][:limit]


def _app():
    app = FastAPI()
    app.state.auth_service = FakeAuthService()
    repository = FakeLeaderboardRepository()
    app.state.race_results = repository
    app.include_router(leaderboard_router, prefix='/v1')
    return app, repository


def _auth(token: str):
    return {'Authorization': f'Bearer {token}'}


def test_official_leaderboard_requires_current_pro_entitlement():
    app, repository = _app()

    with TestClient(app) as client:
        assert client.get('/v1/ranked/leaderboard').status_code == 401
        assert client.get('/v1/ranked/leaderboard', headers=_auth('free')).status_code == 403
        assert client.get('/v1/ranked/leaderboard', headers=_auth('grace')).status_code == 403
        assert client.get('/v1/ranked/leaderboard', headers=_auth('expired')).status_code == 403

        response = client.get('/v1/ranked/leaderboard?limit=2', headers=_auth('pro'))

    assert response.status_code == 200
    assert repository.limits == [2]
    assert response.json() == {
        'entries': [
            {
                'user_id': 'alpha',
                'rating': 1420.0,
                'games_played': 31,
                'position': 1,
                'is_top_1000': True,
            },
            {
                'user_id': 'beta',
                'rating': 1390.5,
                'games_played': 28,
                'position': 1000,
                'is_top_1000': True,
            },
        ]
    }


def test_leaderboard_limit_is_http_bounded_to_one_through_one_hundred():
    app, repository = _app()

    with TestClient(app) as client:
        assert client.get('/v1/ranked/leaderboard?limit=0', headers=_auth('pro')).status_code == 422
        assert client.get('/v1/ranked/leaderboard?limit=101', headers=_auth('pro')).status_code == 422
        defaulted = client.get('/v1/ranked/leaderboard', headers=_auth('pro'))

    assert defaulted.status_code == 200
    assert repository.limits == [100]


def test_leaderboard_ignores_client_attempts_to_supply_authoritative_fields():
    app, repository = _app()

    with TestClient(app) as client:
        response = client.get(
            '/v1/ranked/leaderboard?limit=1&rating=999999&position=1&is_pro=true',
            headers=_auth('pro'),
        )

    assert response.status_code == 200
    assert repository.limits == [1]
    assert response.json()['entries'][0]['rating'] == 1420.0
    assert response.json()['entries'][0]['position'] == 1
