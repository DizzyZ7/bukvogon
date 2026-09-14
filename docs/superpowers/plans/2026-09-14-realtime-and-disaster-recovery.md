# Realtime and Disaster Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build horizontally scalable realtime race sessions with bounded server load, durable completed results, persistent container storage, and automatic encrypted weekly PostgreSQL backups delivered to Telegram.

**Architecture:** Redis is the shared hot-state layer for active races, distributed mutation locks and pub/sub; PostgreSQL stores durable completed results only. FastAPI workers expose HTTP/WebSocket race contracts with bounded message size/update cadence. PostgreSQL/Redis Docker volumes provide primary persistence while an isolated backup container creates validated, age-encrypted weekly full dumps and delivers them in Telegram-safe chunks.

**Tech Stack:** Python 3.12, FastAPI, WebSocket, redis-py, asyncpg, Redis 8 AOF, PostgreSQL 17, Docker Compose, age, Bash, Telegram Bot API, pytest.

**Spec:** `docs/superpowers/specs/2026-09-14-realtime-session-design.md` and `docs/superpowers/specs/2026-09-14-database-disaster-recovery-design.md`

## Global Constraints

- Maximum 6 racers per initial race.
- Active race TTL is 20 minutes.
- WebSocket payload maximum is 2048 bytes.
- Accepted progress cadence is bounded to approximately 10–12 Hz per player.
- PostgreSQL is never written once per character.
- Completed result persistence happens outside the race mutation lock.
- Redis hot state uses AOF persistence and a named volume.
- PostgreSQL uses a named persistent volume.
- Weekly backup runs Sunday 04:15 UTC.
- Raw database dumps are never delivered through Telegram.
- Production backup host contains only an age public recipient, not the private identity.

---

### Task 1: Server-authoritative race domain

**Files:**
- Create: `apps/api/bukvogon/domain/race_session.py`
- Create: `apps/api/tests/test_race_sessions.py`

**Interfaces:**
- Produces: `RaceSession`, `RacePlayerState`, `MAX_RACE_PLAYERS`, `RACE_TTL_SECONDS`.

- [x] Write tests for player capacity, monotonic progress, bounds, finish ordering and duplicate completion.
- [x] Verify tests fail before implementation.
- [x] Implement minimal race domain.
- [x] Verify tests pass.

### Task 2: Shared Redis hot-state

**Files:**
- Create: `apps/api/bukvogon/infrastructure/redis_races.py`
- Create: `apps/api/tests/test_redis_race_store.py`
- Modify: `apps/api/bukvogon/services/races.py`

**Interfaces:**
- Produces: `RedisRaceStore`, `RedisMutationLock`, `RedisRaceBroker`.

- [x] Test JSON round-trip, TTL refresh and pub/sub.
- [x] Test that race mutations use the store-level lock.
- [x] Implement token-safe distributed lock using Redis SET NX PX + WATCH/MULTI release.
- [x] Verify Redis-backed tests pass with fakeredis.

### Task 3: Bounded realtime protocol and fan-out

**Files:**
- Create: `apps/api/bukvogon/domain/race_protocol.py`
- Create: `apps/api/bukvogon/services/realtime.py`
- Create: `apps/api/bukvogon/api/race_routes.py`
- Create: `apps/api/tests/test_race_protocol.py`
- Create: `apps/api/tests/test_realtime_hub.py`
- Create: `apps/api/tests/test_realtime_api.py`

**Interfaces:**
- Consumes: `RaceService`, shared Redis broker/store.
- Produces: POST/GET race endpoints and WebSocket progress/snapshot protocol.

- [x] Reject oversized or unknown WebSocket messages.
- [x] Rate-limit accepted progress events with an 80 ms minimum interval.
- [x] Use one Redis pub/sub listener per race per API process, not per socket.
- [x] Broadcast snapshots to all local clients.
- [x] Reject WebSocket player IDs that are not members of the race.

### Task 4: Durable result persistence

**Files:**
- Create: `apps/api/bukvogon/infrastructure/postgres_results.py`
- Create: `apps/api/tests/test_postgres_results.py`
- Modify: `apps/api/bukvogon/services/races.py`

**Interfaces:**
- Produces: `PostgresRaceResultRepository.persist(PersistedRaceResult)`.

- [x] Use a lazy asyncpg pool with min 1 / max 5 connections per worker.
- [x] Create the result table idempotently.
- [x] Upsert by `(race_id, player_id)` for retry safety.
- [x] Verify intermediate progress causes no durable write.
- [x] Verify finish persistence runs after releasing the race lock.

### Task 5: Production API runtime

**Files:**
- Modify: `apps/api/bukvogon/main.py`
- Create: `apps/api/Dockerfile`
- Create: `apps/api/tests/test_deployment_contract.py`
- Modify: `docker-compose.yml`

**Interfaces:**
- Production Redis/PostgreSQL wiring through environment variables.

- [x] Wire Redis store/broker, realtime hub and PostgreSQL result repository in FastAPI lifespan.
- [x] Run two Uvicorn workers by default.
- [x] Add per-worker concurrency bound.
- [x] Add Docker health dependencies for Redis/PostgreSQL/API.

### Task 6: Persistent storage and weekly encrypted backup

**Files:**
- Modify: `docker-compose.yml`
- Create: `.env.example`
- Create: `ops/backup/Dockerfile`
- Create: `ops/backup/backup.sh`
- Create: `ops/backup/restore.sh`
- Create: `ops/backup/crontab`
- Create: `apps/api/tests/test_backup_contract.py`

**Interfaces:**
- Backup requires `POSTGRES_*`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID`, `BACKUP_AGE_RECIPIENT`.
- Restore additionally requires `BACKUP_AGE_IDENTITY_FILE` and `RESTORE_CONFIRM=YES`.

- [x] Persist PostgreSQL under `pgdata`.
- [x] Persist Redis AOF under `redisdata`.
- [x] Validate dump with `pg_restore --list`.
- [x] Encrypt to public age recipient.
- [x] SHA-256 and split encrypted archive into 45 MiB pieces.
- [x] Send summary, manifest, checksums and every part to Telegram.
- [x] Keep local encrypted generations for 35 days.
- [x] Restore verifies all checksums before decrypting/restoring.

### Task 7: CI and documentation

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `README.md`

- [x] Run complete backend tests.
- [x] Run complete web tests and production build.
- [x] Validate Bash syntax.
- [x] Validate Docker Compose configuration.
- [x] Build API and backup Docker images in CI.
- [x] Document secrets, backup key separation, manual backup and restore flow.
