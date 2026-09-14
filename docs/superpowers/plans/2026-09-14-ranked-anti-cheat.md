# Ranked Anti-Cheat Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Protect Ranked/MMR/Top-1000 with challenge-bound race telemetry, deterministic low-cost risk scoring, provisional result verification, and server-owned leaderboard eligibility.

**Architecture:** Ranked receives a server-created one-time challenge stored in Redis. Existing bounded WebSocket traffic carries compact race-only telemetry batches; the server validates challenge/sequence/text progress, accumulates bounded evidence, computes a deterministic risk score at finish, and persists one compact verification summary per Ranked result. Casual stays unchanged.

**Tech Stack:** Python 3.12, FastAPI/WebSocket, Redis, asyncpg/PostgreSQL, TypeScript 7, Vitest, Next.js 16.

**Spec:** `docs/superpowers/specs/2026-09-14-ranked-anti-cheat-design.md`

## Global Constraints

- Client is untrusted; verification/risk/leaderboard status are server-owned.
- High CPM alone never invalidates or bans a result.
- Ranked paste/drop/autofill that advances text is invalid.
- No per-key PostgreSQL writes and no external AI/LLM scoring.
- Telemetry captures only race-focused gameplay input.
- `verified` is required before Ranked result can affect MMR/official leaderboard/Top-1000 prestige.
- MVP issues no permanent automatic account bans.

---

### Task 1: Deterministic anti-cheat domain

**Files:**
- Create: `apps/api/tests/test_anti_cheat.py`
- Create: `apps/api/bukvogon/domain/anti_cheat.py`

**Interfaces:**
- Produces: `VerificationStatus`, `TelemetryEvent`, `TelemetryEvidence`, `AntiCheatDecision`, `evaluate_evidence()`.

- [ ] Write failing tests for normal varied timing, fast varied timing, periodic scripted timing, sparse telemetry, paste, progress mismatch and hard invalidation.
- [ ] Verify RED in GitHub Actions.
- [ ] Implement deterministic feature extraction/risk reasons/decision thresholds.
- [ ] Verify GREEN.

### Task 2: Challenge-bound Ranked protocol

**Files:**
- Create: `apps/api/tests/test_ranked_telemetry_protocol.py`
- Modify: `apps/api/bukvogon/domain/race_protocol.py`

**Interfaces:**
- Produces: strict `RankedTelemetryBatch` parser with `challenge_id`, `nonce`, `batch_seq`, confirmed progress fragment and compact input events.

- [ ] Write failing tests for unknown fields, replayable/invalid sequence shape, oversized event lists, invalid kinds, invalid deltas and valid bounded batch.
- [ ] Verify RED.
- [ ] Implement minimal parser while preserving existing Casual `ProgressEvent` contract.
- [ ] Verify GREEN.

### Task 3: Redis challenge/replay state

**Files:**
- Create: `apps/api/tests/test_redis_anti_cheat.py`
- Create: `apps/api/bukvogon/infrastructure/redis_anti_cheat.py`

**Interfaces:**
- Produces: `RedisAntiCheatStore.issue_challenge()`, `validate_and_advance()`, `append_evidence()`, `get_evidence()`, `finalize()`.

- [ ] Write failing tests for binding, expiry, wrong nonce, duplicate/out-of-order batch sequence and bounded evidence retention.
- [ ] Verify RED.
- [ ] Implement Redis challenge/evidence state with race TTL and atomic sequence advancement.
- [ ] Verify GREEN.

### Task 4: Ranked verification orchestration and durable status

**Files:**
- Create: `apps/api/tests/test_ranked_verification_service.py`
- Create: `apps/api/bukvogon/services/anti_cheat.py`
- Modify: `apps/api/bukvogon/services/races.py`
- Modify: `apps/api/bukvogon/infrastructure/postgres_results.py`
- Modify/add tests: `apps/api/tests/test_postgres_results.py`

**Interfaces:**
- Produces: provisional persisted result, idempotent status transition to `verified/review/invalid`, bounded risk/reason/audit metadata.

- [ ] Write failing tests proving intermediate progress never persists evidence, finish starts provisional, invalid/review never mutate competitive eligibility, and verified transition is idempotent.
- [ ] Verify RED.
- [ ] Add verification columns/upsert/update contract and orchestration.
- [ ] Verify GREEN.

### Task 5: Ranked API/WebSocket challenge and telemetry flow

**Files:**
- Create/modify: `apps/api/tests/test_realtime_api.py`
- Modify: `apps/api/bukvogon/api/race_routes.py`
- Modify: `apps/api/bukvogon/main.py`

**Interfaces:**
- Ranked race creation/join returns challenge metadata; telemetry batches are validated before progress mutation; invalid challenge cannot publish a verified result.

- [ ] Write failing integration tests for challenge happy path, wrong nonce, replayed batch, paste invalidation and reconnect sequence resume.
- [ ] Verify RED.
- [ ] Wire anti-cheat service/store into app lifespan and WebSocket flow.
- [ ] Verify GREEN.

### Task 6: Browser race-only telemetry collector

**Files:**
- Create: `apps/web/lib/ranked-telemetry.test.ts`
- Create: `apps/web/lib/ranked-telemetry.ts`

**Interfaces:**
- Produces a client-side collector that records only focused race input metadata, never global keyboard events, batches `beforeinput`/correction/provenance data, and returns bounded payloads for the existing WebSocket sender.

- [ ] Write failing Vitest cases for trusted insert, backspace, paste flag, focus/visibility metadata, sequence increments and bounded buffer.
- [ ] Verify RED.
- [ ] Implement collector as a pure library ready for the live typing component.
- [ ] Verify GREEN and production build.

### Task 7: Competitive eligibility + docs/CI

**Files:**
- Modify/add tests around leaderboard/prestige eligibility.
- Modify: `README.md`
- Modify: PR description.

**Interfaces:**
- Only server-verified results may improve official leaderboard/MMR or produce Top-1000 prestige.

- [ ] Add regression tests for verified-only eligibility.
- [ ] Run all backend tests, web tests and production build.
- [ ] Confirm latest GitHub Actions run is green.
- [ ] Document shadow-mode rollout, privacy and operational tuning.