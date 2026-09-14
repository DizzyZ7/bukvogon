# BukvoGon server identity and entitlement design

Date: 2026-09-14
Status: proposed for implementation
Scope: API identity, session security, server-owned Pro entitlement, Ranked authorization, one-time WebSocket tickets, official leaderboard authorization

## 1. Goal

Close the remaining Ranked trust boundary. A client must not be able to gain Ranked access, obtain a Ranked challenge, connect to a Ranked WebSocket, apply MMR, or read the official leaderboard by supplying an arbitrary `player_id`, entitlement flag, verification state, rating, or leaderboard position.

The server becomes authoritative for identity and entitlement. Existing race verification, exactly-once MMR, leaderboard projection, and public prestige remain unchanged in principle and consume the authenticated user identity rather than client-owned identity claims.

## 2. Non-goals

This slice does not implement passwords, email verification, Telegram login, OAuth, billing-provider integration, account recovery, device management, or admin UI. It establishes the identity/session boundary those features will later attach to.

No payment provider is called during Ranked authorization. Future payment webhooks update local entitlement state in PostgreSQL.

## 3. Chosen approach

Use opaque Bearer sessions rather than self-contained JWTs.

A session token is generated with cryptographically secure randomness and returned to the client only once. PostgreSQL stores only a SHA-256 digest of the token, never the raw bearer credential.

Reasons:
- immediate revocation and expiry are simple;
- entitlement changes are observed immediately without waiting for token expiry;
- future account linking does not change the Ranked API contract;
- no signing-key rotation or JWT claim-staleness problem is introduced in this MVP;
- session inspection remains server-side and auditable.

Default session lifetime is 30 days. Expiry is stored server-side and checked on every authenticated request.

## 4. Data model

### `users`

- `user_id TEXT PRIMARY KEY`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

The first implementation creates anonymous/guest users. The identifier is stable and server-generated. Later identity providers attach to this user rather than replacing it.

### `auth_sessions`

- `session_id TEXT PRIMARY KEY`
- `user_id TEXT NOT NULL REFERENCES users(user_id)`
- `token_hash BYTEA NOT NULL UNIQUE`
- `created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`
- `expires_at TIMESTAMPTZ NOT NULL`
- `revoked_at TIMESTAMPTZ NULL`

Only active, non-expired, non-revoked sessions authenticate.

### `user_entitlements`

- `user_id TEXT PRIMARY KEY REFERENCES users(user_id)`
- `status TEXT NOT NULL DEFAULT 'free'`
- `valid_until TIMESTAMPTZ NULL`
- `updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()`

Valid statuses stay aligned with the existing domain enum:
- `free`
- `pro_active`
- `pro_grace`
- `pro_expired`

Only `pro_active` whose `valid_until` is either NULL or in the future may enter Ranked or view the official leaderboard.

## 5. Authentication API

### `POST /v1/auth/guest`

Creates a server-owned user, a default FREE entitlement row, and a new opaque session with a 30-day expiry.

Response:

```json
{
  "user_id": "...",
  "access_token": "...",
  "token_type": "bearer",
  "expires_at": "..."
}
```

The raw access token is never persisted.

### `GET /v1/auth/me`

Requires `Authorization: Bearer <token>` and returns the authenticated user plus current server-owned entitlement.

### `POST /v1/auth/logout`

Requires the active Bearer session and revokes that exact session. The raw token is still never stored. Reusing the same token after logout returns HTTP 401.

## 6. FastAPI identity boundary

Introduce one reusable dependency that:

1. Parses the Bearer header.
2. Hashes the supplied token with SHA-256.
3. Looks up the session by digest.
4. Rejects missing, unknown, expired, or revoked sessions with HTTP 401.
5. Loads the local entitlement.
6. Returns an immutable authenticated principal containing `user_id` and `Entitlement`.

A second dependency enforces active Pro and returns HTTP 403 when authentication is valid but entitlement does not allow Ranked.

The client never supplies an entitlement status to a protected endpoint.

## 7. Ranked race authorization

### Race creation

`POST /v1/ranked/races` requires an authenticated active-Pro caller.

Until matchmaking owns race assembly, the endpoint may continue accepting `player_ids` as orchestration input, but they are not trusted identity assertions. Before creating an official Ranked race the server must verify:
- the authenticated caller is included in `player_ids`;
- every id resolves to an existing server user;
- every listed user has a current active-Pro entitlement;
- duplicates are rejected;
- normal race-size bounds still apply.

This prevents a client from constructing an official Ranked race with fake, unknown, FREE, GRACE, or EXPIRED participants. It does not yet implement invitation consent; matchmaking will replace client-authored participant lists later.

### Challenge issuance

Replace the trusted identity surface:

Current:
`POST /v1/ranked/races/{race_id}/challenge/{player_id}`

Target:
`POST /v1/ranked/races/{race_id}/challenge`

The server derives `player_id` from the authenticated principal. It verifies:
- session is valid;
- entitlement is active Pro;
- race exists and is Ranked;
- authenticated user belongs to the race.

The challenge remains idempotently bound in Redis to `race_id + authenticated user_id`.

No request field can override this identity.

## 8. Ranked WebSocket authorization

Bearer tokens must not be placed in WebSocket URLs because URLs can be logged, cached, copied, and retained by intermediaries.

Challenge issuance also returns a short-lived one-time WebSocket ticket.

Ticket properties:
- cryptographically random;
- stored in Redis only as server-side state;
- TTL: 30 seconds;
- bound to `user_id + race_id + challenge_id`;
- consumed atomically once;
- reuse fails;
- wrong race/user/challenge fails;
- expiry fails.

Target Ranked WebSocket route:

`/v1/ranked/races/{race_id}/ws/{challenge_id}?ticket=<opaque_ticket>`

The path no longer contains `player_id`. After consuming the ticket, the server obtains the user id from ticket state and uses that id throughout the socket lifetime.

The ticket is a WebSocket bootstrap credential, not a reusable login session.

## 9. Official leaderboard authorization

Expose:

`GET /v1/ranked/leaderboard?limit=...`

Requirements:
- valid authenticated session;
- active Pro entitlement;
- limit is bounded server-side;
- rows come only from the authoritative `ranked_player_ratings` projection;
- leaderboard position is computed server-side;
- `is_top_1000` is derived from position 1..1000;
- no client `pro`, rank, rating, or position parameter exists.

FREE, PRO_GRACE, and PRO_EXPIRED users receive HTTP 403. Anonymous callers receive HTTP 401.

## 10. MMR ownership

The current `POST /v1/ranked/rate` already accepts only `race_id` and applies server-owned verified results and server-owned ratings exactly once.

This design keeps that property. The endpoint must not regain any client-owned player/rating/status inputs while auth is added.

Whether this endpoint is public to clients or eventually moved behind an internal race-finalization service is a later orchestration decision. In either case, its calculation inputs remain server-owned.

## 11. Entitlement ownership and future payments

The local PostgreSQL entitlement row is authoritative for request-time access decisions.

Future billing flow:
1. payment provider sends signed webhook;
2. webhook adapter validates provider signature/idempotency;
3. application updates `user_entitlements`;
4. Ranked requests immediately observe the new local status.

The API never calls the payment provider synchronously to decide whether a user may play Ranked.

There is no public endpoint that lets a user set `pro_active` for themselves.

## 12. Security properties

The implementation must guarantee:
- raw session tokens are never stored in PostgreSQL;
- raw session tokens are not logged by application code;
- session comparison is performed by indexed hash lookup;
- revoked and expired sessions fail closed;
- entitlement is loaded server-side;
- official Ranked participant ids resolve to real active-Pro users before race creation;
- player identity is never accepted from client input on authenticated Ranked challenge/socket paths;
- WebSocket tickets are one-time, short-lived, and binding-specific;
- duplicate ticket consumption is rejected atomically;
- auth failure is 401, entitlement failure is 403;
- no fallback treats missing auth as FREE for a protected Ranked endpoint;
- no client-supplied status can unlock official leaderboard or Top-1000 prestige.

## 13. Failure behavior

- Missing/malformed Bearer token -> 401.
- Unknown/revoked/expired session -> 401.
- Valid session without current Pro -> 403.
- Ranked race creation with unknown/non-Pro participants -> 422.
- Authenticated caller omitted from its client-authored Ranked participant list -> 403.
- Authenticated user not in Ranked race -> 403.
- Missing/expired/consumed/mismatched WebSocket ticket -> close with policy violation code 1008 before joining the realtime hub.
- Missing race -> 404 for HTTP challenge issuance; socket closes 1008.
- Infrastructure errors do not downgrade to anonymous/FREE behavior; protected paths fail closed.

## 14. Components

Planned focused units:

- `domain/auth.py`: immutable principal/session-facing domain values and token hashing helpers if appropriate.
- `infrastructure/postgres_auth.py`: user/session/entitlement persistence.
- `infrastructure/redis_ws_tickets.py`: one-time short-lived ticket store.
- `services/auth.py`: session issuance and principal resolution.
- `api/auth_routes.py`: guest session, `/auth/me`, and logout.
- reusable FastAPI auth/Pro dependencies.
- existing `race_routes.py`: replace trusted Ranked player identity with authenticated principal and ticket consumption.
- existing leaderboard repository projection: expose only through Pro-gated API.
- `main.py`: wire repositories/services into app state and lifecycle.

Files may be split further if route or infrastructure modules grow beyond a clear single responsibility.

## 15. TDD contract

Implementation proceeds RED -> GREEN in these slices:

1. Session token hashing: raw token never persists.
2. Guest issuance creates user + FREE entitlement + 30-day session.
3. Principal resolution accepts active sessions and rejects unknown/revoked/expired sessions.
4. Logout revokes the exact session and replay returns 401.
5. Pro dependency allows only current `pro_active`.
6. Ranked creation rejects unknown/non-Pro participants and requires the caller in the race.
7. Ranked challenge derives user id from auth and cannot be spoofed with a path/body `player_id`.
8. WebSocket ticket is bound, expires, and is consumable exactly once.
9. Ranked socket uses ticket-owned user id and rejects replay/mismatch before hub join.
10. Official leaderboard endpoint is 401/403 gated and returns server projection only.
11. Existing exactly-once MMR and anti-cheat suites remain green.
12. Full GitHub Actions backend, web build/tests, and operations/backup validation remain green.

## 16. Migration and compatibility

This branch is still pre-production, so protected Ranked endpoint contracts may intentionally change rather than retain insecure compatibility aliases.

Casual race routes remain unchanged in this slice unless shared auth wiring requires a non-behavioral refactor.

Existing tests that directly inject repositories into `app.state` should continue to be supported through dependency boundaries or updated to inject the new auth service explicitly.

## 17. Acceptance criteria

The slice is complete when:
- a guest can obtain a server session with a 30-day expiry;
- raw bearer credentials are not persisted;
- logout/revocation invalidates the session immediately;
- only the session token holder can act as that user on protected Ranked endpoints;
- only active Pro can create/join official Ranked races or view official leaderboard data;
- every official Ranked participant is a real active-Pro server user;
- challenge and socket identity no longer come from client `player_id`;
- the Ranked WebSocket bootstrap credential is short-lived and one-use;
- official leaderboard/Top-1000 data is entirely server-derived;
- no public route can self-grant Pro;
- current anti-cheat and exactly-once MMR guarantees remain intact;
- complete CI is green on the PR head.
