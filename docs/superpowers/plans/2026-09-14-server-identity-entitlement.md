# Server Identity and Entitlement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make BukvoGon Ranked identity and Pro entitlement fully server-authoritative, with hash-only opaque sessions, one-time WebSocket tickets, and a Pro-gated official leaderboard.

**Architecture:** PostgreSQL owns users, session digests, entitlements, durable race results, ratings, and the exactly-once rating ledger. FastAPI resolves an immutable authenticated principal from a Bearer token and derives Ranked player identity from that principal. Redis owns short-lived one-time WebSocket bootstrap tickets bound to user/race/challenge. Existing anti-cheat, MMR, and leaderboard projections remain authoritative and are consumed only after auth/entitlement checks. MMR is finalized server-side after the last participant has finished and verification allows competitive application; there is no public client endpoint that can trigger rating application.

**Tech Stack:** Python 3.12, FastAPI, Pydantic, asyncpg/PostgreSQL, redis.asyncio/Redis, pytest/fakeredis, existing BukvoGon domain/services.

**Spec:** `docs/superpowers/specs/2026-09-14-server-identity-entitlement-design.md`

## Global Constraints

- Raw session tokens are never stored in PostgreSQL or application logs.
- Session tokens are opaque, cryptographically random, and expire after 30 days by default.
- Only current `pro_active` entitlement may enter Ranked or view the official leaderboard.
- Authentication failure returns 401; valid identity without Pro returns 403.
- Ranked challenge/socket player identity is never accepted from client input.
- WebSocket tickets live 30 seconds, are bound to `user_id + race_id + challenge_id`, and are atomically single-use.
- Ranked rating application has no public client trigger and is server-owned/exactly-once by `race_id`.
- Casual routes remain behaviorally unchanged.
- Existing anti-cheat, exactly-once MMR, and server-owned Top-1000 guarantees must remain green.

---

### Task 1: Auth domain and token hashing

**Files:**
- Create: `apps/api/bukvogon/domain/auth.py`
- Test: `apps/api/tests/test_auth_domain.py`

**Interfaces:**
- Produces: `AuthenticatedPrincipal`, `IssuedSession`, `hash_session_token(token: str) -> bytes`, `generate_session_token() -> str`.

- [x] **Step 1: Write failing tests** for deterministic SHA-256 hashing, distinct random tokens, and immutable principal/session values.
- [x] **Step 2: Run** `python -m pytest tests/test_auth_domain.py -v`; expect import/module failure.
- [x] **Step 3: Implement minimal domain code** using `hashlib.sha256` and `secrets.token_urlsafe(32)`; no logging.
- [x] **Step 4: Re-run focused tests** and expect PASS.
- [x] **Step 5: Commit** `feat(api): add auth domain primitives`.

### Task 2: PostgreSQL guest users, sessions, entitlements, logout

**Files:**
- Create: `apps/api/bukvogon/infrastructure/postgres_auth.py`
- Test: `apps/api/tests/test_postgres_auth.py`

**Interfaces:**
- Consumes: `hash_session_token`, existing `Entitlement` / `EntitlementStatus`.
- Produces: `PostgresAuthRepository.create_guest_session()`, `resolve_session(token_hash)`, `revoke_session(token_hash)`, `get_entitlement(user_id)`, `get_entitlements(user_ids)`.

- [x] **Step 1: Write failing repository tests** asserting guest creation creates `users`, FREE `user_entitlements`, and `auth_sessions` with digest only; raw token must not occur in persisted query arguments.
- [x] **Step 2: Add tests** for expired/revoked session rejection, 30-day default expiry, logout revocation, and bulk entitlement loading for Ranked participant validation.
- [x] **Step 3: Run focused tests**; expect missing repository failure.
- [x] **Step 4: Implement three tables** (`users`, `auth_sessions`, `user_entitlements`) and lazy schema initialization consistent with existing repository style.
- [x] **Step 5: Implement transactional guest creation**: generate user/session ids server-side, persist SHA-256 digest only, default FREE entitlement, return raw credential only from method result.
- [x] **Step 6: Implement fail-closed resolution/revocation** and bulk entitlement lookup.
- [x] **Step 7: Re-run focused tests** and commit `feat(api): persist server auth sessions and entitlements`.

### Task 3: Auth service, FastAPI dependencies, guest/me/logout API

**Files:**
- Create: `apps/api/bukvogon/services/auth.py`
- Create: `apps/api/bukvogon/api/auth.py`
- Modify: `apps/api/bukvogon/main.py`
- Test: `apps/api/tests/test_auth_api.py`

**Interfaces:**
- Produces: `AuthService.issue_guest()`, `resolve_bearer()`, `logout()`, `require_authenticated_principal`, `require_pro_principal`.

- [x] **Step 1: Write failing API tests** for `POST /v1/auth/guest`, `GET /v1/auth/me`, `POST /v1/auth/logout`, missing/malformed Bearer 401, revoked/expired token 401, FREE principal 403 through Pro dependency, current Pro accepted.
- [x] **Step 2: Run focused tests** and verify RED.
- [x] **Step 3: Implement `AuthService`** around repository methods; normalize all invalid credentials to authentication failure without leaking whether a digest existed.
- [x] **Step 4: Implement FastAPI Bearer parsing/dependencies**; never interpret missing auth as FREE on protected endpoints.
- [x] **Step 5: Add auth routes and wire service/repository lifecycle in `main.py`**.
- [x] **Step 6: Re-run auth API + existing backend tests** and commit `feat(api): add opaque session authentication`.

### Task 4: Redis one-time WebSocket tickets

**Files:**
- Create: `apps/api/bukvogon/infrastructure/redis_ws_tickets.py`
- Test: `apps/api/tests/test_redis_ws_tickets.py`

**Interfaces:**
- Produces: `WsTicketGrant`, `RedisWsTicketStore.issue(user_id, race_id, challenge_id)`, `consume(ticket, race_id, challenge_id)` returning authoritative `user_id`.

- [x] **Step 1: Write failing tests** for 30-second TTL, wrong race/challenge rejection, exact user/race/challenge binding, atomic single-use, and expiration.
- [x] **Step 2: Run focused tests** and verify RED.
- [x] **Step 3: Implement random opaque ticket** stored under a SHA-256-derived Redis key or non-guessable ticket key, with compact JSON binding state and `SET NX EX 30`.
- [x] **Step 4: Implement atomic consume** with validation-before-consumption transaction semantics.
- [x] **Step 5: Re-run focused tests** and commit `feat(api): add one-time ranked websocket tickets`.

### Task 5: Protect Ranked creation, challenge, and WebSocket identity

**Files:**
- Modify: `apps/api/bukvogon/api/race_routes.py`
- Modify: `apps/api/bukvogon/main.py`
- Test/update: `apps/api/tests/test_ranked_realtime_api.py`

**Interfaces:**
- Consumes: `require_pro_principal`, `PostgresAuthRepository.get_entitlements`, `RedisWsTicketStore`, existing `RankedAntiCheatService`.
- Produces secure routes:
  - `POST /v1/ranked/races`
  - `POST /v1/ranked/races/{race_id}/challenge`
  - `/v1/ranked/races/{race_id}/ws/{challenge_id}?ticket=...`

- [x] **Step 1: Write failing tests** proving FREE cannot create/enter Ranked, active Pro can, every requested participant must have current Pro, authenticated user must be included, and client cannot spoof challenge identity with path/body `player_id`.
- [x] **Step 2: Add WebSocket tests** proving ticket-owned identity is used, replay/wrong binding closes 1008 before hub join, and raw Bearer session token is absent from the URL contract.
- [x] **Step 3: Run focused tests** and verify RED.
- [x] **Step 4: Remove `player_id` from Ranked challenge and socket route contracts**; derive identity from principal/ticket only.
- [x] **Step 5: Make challenge issuance return `ws_ticket` plus challenge data**; ticket binds to the newly issued/reused challenge id.
- [x] **Step 6: Validate all Ranked race participants from server entitlement rows** before race creation; no client entitlement flags.
- [x] **Step 7: Re-run Ranked/auth/anti-cheat/realtime tests** and commit `feat(api): enforce authenticated pro ranked identity`.

### Task 6: Pro-gated official leaderboard

**Files:**
- Create: `apps/api/bukvogon/api/leaderboard.py`
- Modify: `apps/api/bukvogon/main.py`
- Test: `apps/api/tests/test_ranked_leaderboard_api.py`

**Interfaces:**
- Consumes: existing `RankedLeaderboardEntry`, server leaderboard projection, `require_pro_principal`.
- Produces: `GET /v1/ranked/leaderboard?limit=N` with bounded `1 <= N <= 100`, official position and server-derived `is_top_1000` only.

- [x] **Step 1: Write failing endpoint tests**: anonymous 401, FREE/GRACE/EXPIRED 403, PRO_ACTIVE 200, oversized/invalid limit rejected, no client rating/position/pro fields accepted.
- [x] **Step 2: Run focused tests** and verify RED.
- [x] **Step 3: Expose repository projection** ordered by existing deterministic rule and return only server-owned fields.
- [x] **Step 4: Add Pro-gated route** and preserve server-derived Top-1000 semantics.
- [x] **Step 5: Run full backend suite**.
- [x] **Step 6: Verify complete GitHub Actions**.

### Task 7: Remove client-owned MMR trigger and finalize rating server-side

**Files:**
- Modify: `apps/api/bukvogon/api/routes.py`
- Modify: `apps/api/bukvogon/api/models.py`
- Modify: `apps/api/bukvogon/api/race_routes.py`
- Modify: `apps/api/tests/test_api.py`
- Modify: `apps/api/tests/test_ranked_realtime_api.py`

**Behavior:**
- `/v1/ranked/rate` does not exist publicly.
- A finisher is verified first.
- Rating application is attempted only when the race contains at least two racers and every racer has an authoritative finish place.
- PostgreSQL verification state remains the final competitive gate; `review`/`invalid` results cannot update MMR.
- Existing unique `race_id` ledger keeps application exactly-once even if multiple server paths race to finalize.

- [x] **Step 1: Write RED tests** for removed public trigger and automatic application after the last verified finisher.
- [x] **Step 2: Verify clean RED**: old route returns 200; automatic ledger call is absent.
- [x] **Step 3: Remove HTTP route and obsolete request/response models.**
- [x] **Step 4: Trigger server-owned `apply_ranked_rating(race_id)` after finish verification when race finish state is complete.**
- [x] **Step 5: Keep verified-only fail-closed behavior through the durable repository gate.**
- [x] **Step 6: Verify GitHub Actions run #268 (`34866722014`)**: backend, web tests/build, operations/backup validation all success.
