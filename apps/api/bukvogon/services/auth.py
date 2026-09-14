from __future__ import annotations

from typing import Protocol

from bukvogon.domain.auth import AuthenticatedPrincipal, IssuedSession, hash_session_token


class AuthRepository(Protocol):
    async def create_guest_session(self) -> IssuedSession: ...
    async def resolve_session(self, token_hash: bytes) -> AuthenticatedPrincipal | None: ...
    async def revoke_session(self, token_hash: bytes) -> bool: ...


class AuthenticationError(ValueError):
    pass


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository

    async def issue_guest(self) -> IssuedSession:
        return await self._repository.create_guest_session()

    async def resolve_access_token(self, token: str) -> AuthenticatedPrincipal:
        if not token:
            raise AuthenticationError('invalid session')
        principal = await self._repository.resolve_session(hash_session_token(token))
        if principal is None:
            raise AuthenticationError('invalid session')
        return principal

    async def logout(self, token: str) -> bool:
        await self.resolve_access_token(token)
        return await self._repository.revoke_session(hash_session_token(token))
