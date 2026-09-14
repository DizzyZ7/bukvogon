import asyncio
from datetime import datetime, timezone

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from bukvogon.api.auth import auth_router, require_pro_principal
from bukvogon.domain.auth import AuthenticatedPrincipal, IssuedSession, hash_session_token
from bukvogon.domain.entitlements import Entitlement, EntitlementStatus
from bukvogon.services.auth import AuthService, AuthenticationError


class FakeAuthRepository:
    def __init__(self):
        self.issued = IssuedSession('guest-1', 'guest-token', 1_800_000_000)
        self.principal = AuthenticatedPrincipal('guest-1', Entitlement(EntitlementStatus.FREE))
        self.resolved_hashes = []
        self.revoked_hashes = []

    async def create_guest_session(self):
        return self.issued

    async def resolve_session(self, token_hash: bytes):
        self.resolved_hashes.append(token_hash)
        return self.principal

    async def revoke_session(self, token_hash: bytes):
        self.revoked_hashes.append(token_hash)
        return True


class FakeAuthService:
    def __init__(self):
        self.issued = IssuedSession('guest-1', 'guest-token', 1_800_000_000)
        self.tokens = {
            'free-token': AuthenticatedPrincipal(
                'free-user', Entitlement(EntitlementStatus.FREE)
            ),
            'pro-token': AuthenticatedPrincipal(
                'pro-user', Entitlement(EntitlementStatus.PRO_ACTIVE)
            ),
            'expired-pro-token': AuthenticatedPrincipal(
                'expired-pro',
                Entitlement(
                    EntitlementStatus.PRO_ACTIVE,
                    datetime(2020, 1, 1, tzinfo=timezone.utc),
                ),
            ),
        }
        self.logged_out = []

    async def issue_guest(self):
        return self.issued

    async def resolve_access_token(self, token: str):
        principal = self.tokens.get(token)
        if principal is None:
            raise AuthenticationError('invalid session')
        return principal

    async def logout(self, token: str):
        await self.resolve_access_token(token)
        self.logged_out.append(token)
        return True


def make_client(service: FakeAuthService):
    app = FastAPI()
    app.state.auth_service = service
    app.include_router(auth_router, prefix='/v1')

    @app.get('/v1/probe/pro')
    async def pro_probe(principal=Depends(require_pro_principal)):
        return {'user_id': principal.user_id}

    return TestClient(app)


def test_auth_service_hashes_credentials_before_repository_access():
    async def scenario():
        repository = FakeAuthRepository()
        service = AuthService(repository)

        issued = await service.issue_guest()
        assert issued == repository.issued

        principal = await service.resolve_access_token('raw-secret')
        assert principal == repository.principal
        assert repository.resolved_hashes == [hash_session_token('raw-secret')]

        assert await service.logout('raw-secret') is True
        assert repository.revoked_hashes == [hash_session_token('raw-secret')]

        repository.principal = None
        with pytest.raises(AuthenticationError, match='invalid session'):
            await service.resolve_access_token('unknown')

    asyncio.run(scenario())


def test_guest_me_and_logout_routes_use_opaque_bearer_session():
    service = FakeAuthService()
    client = make_client(service)

    guest = client.post('/v1/auth/guest')
    assert guest.status_code == 201
    assert guest.json()['user_id'] == 'guest-1'
    assert guest.json()['access_token'] == 'guest-token'
    assert guest.json()['token_type'] == 'bearer'
    assert isinstance(guest.json()['expires_at'], str)

    me = client.get('/v1/auth/me', headers={'Authorization': 'Bearer free-token'})
    assert me.status_code == 200
    assert me.json() == {
        'user_id': 'free-user',
        'entitlement': {'status': 'free', 'valid_until': None},
    }

    logout = client.post('/v1/auth/logout', headers={'Authorization': 'Bearer free-token'})
    assert logout.status_code == 200
    assert logout.json() == {'revoked': True}
    assert service.logged_out == ['free-token']


def test_missing_malformed_unknown_and_expired_sessions_fail_with_401():
    service = FakeAuthService()
    client = make_client(service)

    assert client.get('/v1/auth/me').status_code == 401
    assert client.get('/v1/auth/me', headers={'Authorization': 'Basic abc'}).status_code == 401
    assert client.get('/v1/auth/me', headers={'Authorization': 'Bearer'}).status_code == 401
    assert client.get('/v1/auth/me', headers={'Authorization': 'Bearer unknown'}).status_code == 401


def test_pro_dependency_rejects_free_and_expired_pro_but_accepts_current_pro():
    service = FakeAuthService()
    client = make_client(service)

    free = client.get('/v1/probe/pro', headers={'Authorization': 'Bearer free-token'})
    expired = client.get('/v1/probe/pro', headers={'Authorization': 'Bearer expired-pro-token'})
    active = client.get('/v1/probe/pro', headers={'Authorization': 'Bearer pro-token'})

    assert free.status_code == 403
    assert expired.status_code == 403
    assert active.status_code == 200
    assert active.json() == {'user_id': 'pro-user'}
