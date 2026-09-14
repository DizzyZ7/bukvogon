from dataclasses import FrozenInstanceError

import pytest

from bukvogon.domain.auth import (
    AuthenticatedPrincipal,
    IssuedSession,
    generate_session_token,
    hash_session_token,
)
from bukvogon.domain.entitlements import Entitlement, EntitlementStatus


def test_session_hash_is_deterministic_sha256_bytes_and_does_not_echo_raw_token():
    token = 'bukvogon-secret-token'

    first = hash_session_token(token)
    second = hash_session_token(token)

    assert isinstance(first, bytes)
    assert len(first) == 32
    assert first == second
    assert token.encode('utf-8') not in first


def test_generated_session_tokens_are_nonempty_and_distinct():
    first = generate_session_token()
    second = generate_session_token()

    assert isinstance(first, str)
    assert len(first) >= 32
    assert first != second


def test_authenticated_principal_is_immutable():
    principal = AuthenticatedPrincipal(
        user_id='user-1',
        entitlement=Entitlement(EntitlementStatus.FREE),
    )

    with pytest.raises(FrozenInstanceError):
        principal.user_id = 'spoofed'  # type: ignore[misc]


def test_issued_session_keeps_raw_token_only_in_return_value():
    session = IssuedSession(
        user_id='user-1',
        access_token='raw-token',
        expires_at_epoch=1_800_000_000,
    )

    assert session.user_id == 'user-1'
    assert session.access_token == 'raw-token'
    assert session.expires_at_epoch == 1_800_000_000
