from __future__ import annotations

from dataclasses import dataclass
import hashlib
import secrets

from bukvogon.domain.entitlements import Entitlement


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    user_id: str
    entitlement: Entitlement


@dataclass(frozen=True, slots=True)
class IssuedSession:
    user_id: str
    access_token: str
    expires_at_epoch: int


def generate_session_token() -> str:
    return secrets.token_urlsafe(32)


def hash_session_token(token: str) -> bytes:
    if not token:
        raise ValueError('session token is required')
    return hashlib.sha256(token.encode('utf-8')).digest()
