# Realtime Race Sessions Design

## Goal

Run lightweight server-authoritative BukvoGon races that can support many concurrent players and active sessions without writing every keystroke to PostgreSQL.

## Architecture

- FastAPI owns WebSocket connections and protocol validation.
- A race contains at most 6 active racers for the first production slice.
- Clients send compact progress snapshots, not raw per-keystroke database writes.
- Progress updates are accepted at a maximum useful cadence of 10 Hz per player; faster updates may be coalesced or rejected.
- Redis is the shared hot-state store for active race sessions and has TTL-based cleanup.
- Redis AOF persistence (`appendonly yes`, `appendfsync everysec`) reduces active-session loss during ordinary restarts.
- PostgreSQL is the durable source of truth for completed race results and future player/economy data.
- Durable database writes happen on lifecycle boundaries (race creation/start/finish/result), never once per character.

## Race state

Each participant has:

- `player_id`
- `progress` as validated character offset
- `cpm`
- `accuracy`
- `finished_at` when complete
- `last_update_monotonic`

Each race has:

- `race_id`
- `text_length`
- `status`: waiting / running / finished
- `created_at`
- `expires_at`
- participants

Active race state expires after 20 minutes unless refreshed by valid activity. Finished state may expire sooner after durable results are written.

## WebSocket protocol

Client -> server:

```json
{"type":"progress","offset":142,"cpm":401,"accuracy":0.982}
```

Server -> clients:

```json
{"type":"snapshot","race_id":"...","racers":[...]}
```

Rules:

- progress must never go backwards;
- offset must be between 0 and the race text length;
- payload size is bounded;
- invalid events do not mutate shared state;
- a completed player cannot resume typing in the same race;
- the server is authoritative for completion and place ordering.

## Scaling model

Race state is independent from a single API process. Redis keys are namespaced per race, and Redis pub/sub is the intended fan-out mechanism once multiple FastAPI instances are deployed. A process may maintain only its local WebSocket connection set while shared state remains in Redis.

This keeps horizontal scaling possible behind a load balancer without sticky durable state in Python memory.

## Persistence

PostgreSQL stores completed results. The first durable table records:

- race id;
- player id;
- place;
- CPM;
- accuracy;
- completion timestamp.

No raw key stream is stored in PostgreSQL.

## Failure behavior

- API restart: Redis retains active race state.
- Redis restart: AOF restores recent hot state with approximately one-second persistence granularity under normal operation.
- PostgreSQL outage during finish: result persistence must fail visibly and be retryable; the race state is not immediately discarded.
- Client disconnect: participant state stays until race TTL; reconnect support can be layered on the same race/player identity.

## Resource controls

- 6 players per race for the initial product.
- 20-minute active-race TTL.
- bounded JSON WebSocket messages.
- server-side rate limiting/coalescing of progress events.
- no database transaction per character.

## Testing

Unit tests cover monotonic progress, bounds, finish ordering, duplicate completion, and TTL configuration. API/WebSocket tests cover valid progress and malformed events. Redis/PostgreSQL integration is exercised separately from pure domain logic.