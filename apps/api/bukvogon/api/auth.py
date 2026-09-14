from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status

from bukvogon.domain.auth import AuthenticatedPrincipal
from bukvogon.domain.entitlements import can_play_ranked
from bukvogon.services.auth import AuthService, AuthenticationError


auth_router = APIRouter(prefix='/auth', tags=['auth'])


def _service_from_request(request: Request) -> AuthService:
    return request.app.state.auth_service


def _unauthorized(detail: str = 'invalid or missing bearer session') -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail=detail,
        headers={'WWW-Authenticate': 'Bearer'},
    )


def require_bearer_token(authorization: str | None = Header(default=None)) -> str:
    if authorization is None:
        raise _unauthorized()

    scheme, separator, token = authorization.partition(' ')
    if separator != ' ' or scheme.lower() != 'bearer' or not token.strip():
        raise _unauthorized()
    if ' ' in token.strip():
        raise _unauthorized()
    return token.strip()


async def require_authenticated_principal(
    request: Request,
    token: str = Depends(require_bearer_token),
) -> AuthenticatedPrincipal:
    try:
        return await _service_from_request(request).resolve_access_token(token)
    except AuthenticationError as exc:
        raise _unauthorized() from exc


async def require_pro_principal(
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> AuthenticatedPrincipal:
    if not can_play_ranked(principal.entitlement):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail='active pro subscription required',
        )
    return principal


def _iso_from_epoch(epoch: int) -> str:
    return datetime.fromtimestamp(epoch, tz=timezone.utc).isoformat()


def _entitlement_payload(principal: AuthenticatedPrincipal) -> dict[str, object]:
    valid_until = principal.entitlement.valid_until
    return {
        'status': principal.entitlement.status.value,
        'valid_until': None if valid_until is None else valid_until.isoformat(),
    }


@auth_router.post('/guest', status_code=status.HTTP_201_CREATED)
async def create_guest_session(request: Request) -> dict[str, object]:
    issued = await _service_from_request(request).issue_guest()
    return {
        'user_id': issued.user_id,
        'access_token': issued.access_token,
        'token_type': 'bearer',
        'expires_at': _iso_from_epoch(issued.expires_at_epoch),
    }


@auth_router.get('/me')
async def get_me(
    principal: AuthenticatedPrincipal = Depends(require_authenticated_principal),
) -> dict[str, object]:
    return {
        'user_id': principal.user_id,
        'entitlement': _entitlement_payload(principal),
    }


@auth_router.post('/logout')
async def logout(
    request: Request,
    token: str = Depends(require_bearer_token),
) -> dict[str, bool]:
    service = _service_from_request(request)
    try:
        revoked = await service.logout(token)
    except AuthenticationError as exc:
        raise _unauthorized() from exc
    return {'revoked': revoked}
