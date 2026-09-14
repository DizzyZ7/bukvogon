# BukvoGon Ranked Anti-Cheat Design

## Goal

Protect Ranked, MMR and the official leaderboard from scripted/automated typing while keeping normal players fast to verify, avoiding false bans, and keeping server cost low enough for a small commercial game.

The system cannot mathematically prove that a physical finger pressed every key. Browser and OS automation can imitate human input. The goal is therefore layered evidence: make cheap automation fail, make sophisticated automation statistically visible, and prevent suspicious results from affecting Top-1000 until they are verified.

## Non-goals

- No kernel driver, native anti-cheat or invasive desktop monitoring.
- No recording of keyboard activity outside the BukvoGon race input.
- No automatic account ban based only on high CPM, perfect accuracy, one unusual race, browser `isTrusted`, IP address, or a single statistical feature.
- No AI/LLM call per keypress or per race.
- No pay-to-win or lower anti-cheat requirements for Pro users.

## Trust boundary

The client is untrusted.

Authoritative server inputs are:

- server-created race id;
- server-selected target text and text length;
- one-time race challenge nonce;
- player membership and entitlement;
- monotonic server receive timestamps;
- previously accepted race state;
- Redis anti-replay state;
- stored historical verification summaries.

Client-provided CPM, accuracy, timing and browser event metadata are evidence only. They never directly grant a leaderboard result.

## Ranked challenge

For Ranked, the target text is not delivered as a reusable pre-race asset.

At countdown start the server creates a one-time challenge:

- `race_id`;
- `player_id`;
- `challenge_id`;
- cryptographically random `nonce`;
- target text id/content;
- `issued_at`;
- `start_deadline`, initially 60 seconds after issuance;
- initial event sequence `0`.

The challenge is bound to the race/player pair in Redis. It must be started before `start_deadline`; after the first accepted race input it remains bound to that active race and expires with the race TTL. Reusing a completed/invalidated nonce or submitting events for a different race/player invalidates the run.

The challenge is not intended as a secret once delivered to the browser. Its purpose is freshness, binding and replay resistance, not DRM.

## Input telemetry

Ranked input is captured only while the game input owns focus. The browser batches evidence into existing bounded realtime messages rather than opening a second high-frequency channel.

Each batch contains:

- monotonically increasing `batch_seq`;
- challenge id and nonce;
- current server-validatable confirmed-prefix offset;
- compact input event records since the previous accepted batch;
- cumulative corrections/errors counters;
- current document visibility/focus state.

Each compact event record contains only gameplay metadata:

- `dt_ms`: elapsed client monotonic milliseconds from the prior input event, bounded and integer encoded;
- `kind`: insert, backspace/delete, composition, paste/drop/other;
- `trusted`: browser event `isTrusted` observation;
- `delta`: bounded character-count change;
- `text`: only for insert/composition events, a tightly bounded fragment entered into the BukvoGon race field so the server can compare it with the target text;
- optional input-type category needed to distinguish keyboard text input from paste/composition.

`text` is limited to the active race field and is compared against server-owned target text. The audit stream does not collect key presses outside the race. It does not persist arbitrary global key names, shortcuts, passwords or background keyboard activity.

The target text already exists on the server. The server advances the authoritative confirmed-prefix offset only when accepted gameplay input reconciles with that target. Client-provided offset is therefore a consistency claim, not the source of truth.

## Protocol limits

Existing realtime limits remain the first defense:

- WebSocket message size remains bounded;
- progress/telemetry batches are accepted no faster than the configured realtime cadence;
- batch sequence must strictly increase;
- authoritative confirmed-prefix offset is monotonic and never moves backwards;
- backspaces/corrections are represented in telemetry/counters rather than by decrementing authoritative confirmed progress;
- confirmed offset may not exceed target length;
- cumulative event deltas and inserted race text must be compatible with claimed progress;
- duplicate/replayed batches are ignored or rejected;
- unknown fields/event kinds are rejected.

A player cannot gain progress by sending many messages faster than the server accepts.

## Hard-invalidating signals

The following invalidate the Ranked result without automatically banning the account:

- wrong/expired/replayed challenge;
- player/race binding mismatch;
- impossible sequence jump/replay;
- progress that cannot be reconciled with accepted gameplay input and server target text;
- paste/drop/autofill used to advance Ranked text;
- invalid confirmed offset beyond the text;
- finish received without sufficient accepted event evidence;
- malformed telemetry designed to bypass protocol validation.

The race may still be shown locally as completed, but the result is `invalid`, produces no MMR change and cannot enter a leaderboard.

## Statistical humanity score

Valid protocol traffic receives a deterministic risk score from 0 to 100. The score is calculated from cheap numeric features at race completion; no external AI service is required.

Initial feature groups:

1. **Timing diversity**
   - variance / median absolute deviation of inter-key intervals;
   - ratio of exactly repeated intervals;
   - suspicious periodicity;
   - unrealistically long runs with near-identical timing.

2. **Burst behavior**
   - characters advanced in very short windows;
   - acceleration discontinuities;
   - instantaneous or near-instant sections inconsistent with prior cadence.

3. **Input provenance evidence**
   - fraction of untrusted browser events;
   - paste/drop/composition anomalies;
   - mismatch between event count/deltas/text and progress.

4. **Human correction behavior**
   - error/backspace distribution;
   - correction timing;
   - long perfect runs are weak evidence only, never a ban trigger.

5. **Session consistency**
   - current performance relative to recent verified personal history;
   - simultaneous Ranked sessions for the same account;
   - repeated near-identical timing signatures across races.

High CPM by itself contributes no hard failure. A very fast legitimate typist with natural timing can remain low risk.

## Verification states

Every Ranked result has one of four server-owned states:

- `provisional`: race completed and awaits final risk evaluation;
- `verified`: accepted for MMR and official leaderboard;
- `review`: suspicious enough to withhold official leaderboard/MMR promotion pending additional evidence;
- `invalid`: hard protocol/challenge violation; no MMR/leaderboard effect.

Default thresholds for the first implementation:

- risk `0..34`: `verified`;
- risk `35..100`: `review` unless a hard-invalidating rule applies;
- hard-invalidating rule: `invalid` regardless of score.

These thresholds are configuration, not public protocol constants. We log distributions before tightening them.

No automatic permanent ban is issued by the scoring system in MVP.

## MMR and leaderboard safety

A Ranked finish is first persisted as `provisional`.

Rating/leaderboard mutation occurs only after verification:

- `verified`: eligible for MMR and leaderboard update;
- `review`: race result remains stored but does not improve official rating/leaderboard position until resolved;
- `invalid`: no MMR/leaderboard update;
- a later review can promote `review` to `verified` idempotently.

This means suspicious automation cannot briefly occupy #1 while an asynchronous verifier catches up.

## Top-1000 high-assurance policy

Entering or improving a position inside Top-1000 requires `verified` status plus high-assurance checks.

High assurance means:

- valid fresh challenge;
- enough telemetry coverage for the race;
- no hard-invalidating signals;
- risk below the normal verification threshold;
- no unresolved recent review for the account.

The system may issue an occasional short verification race with a fresh random text when an account first enters a high-value leaderboard band or when risk changes sharply. Verification races grant no bonus MMR and are not used as punishment.

Top-1000 prestige aura/crown is derived only from the verified official leaderboard, never from provisional/review results.

## Storage and privacy

Redis holds active anti-cheat state with the race TTL:

- challenge binding;
- last accepted sequence;
- server-authoritative confirmed prefix;
- rolling counters;
- bounded recent timing window;
- replay markers.

PostgreSQL stores durable result-level evidence:

- verification status;
- numeric risk score;
- normalized reason codes;
- telemetry coverage metrics;
- compact compressed audit trace for Ranked;
- verifier version;
- verified/reviewed timestamps.

The audit trace is bounded. It contains race-only relative timing/input metadata, not global keyboard monitoring.

Normal verified traces should have a configurable retention period (initial target: 30 days). Review/Top-1000 traces may be retained longer for dispute/audit needs. Retention policy must be documented before public launch.

## Cost and load budget

Anti-cheat must remain cheaper than realtime rendering/network fan-out.

Design rules:

- telemetry is batched into the existing approximately 10-12 Hz client-to-server cadence;
- scoring is O(number of accepted gameplay events) for one finished race and uses simple arithmetic;
- no per-key PostgreSQL writes;
- Redis keeps rolling state rather than unbounded event lists;
- PostgreSQL writes the final compact trace/summary once per Ranked participant;
- no external ML API calls;
- leaderboard verification can run asynchronously after durable race completion.

Target compact audit size is low kilobytes per Ranked participant, not raw browser event JSON for every key.

## Abuse controls around Ranked

Separate account/edge controls complement typing telemetry:

- login/signup/payment endpoints may use Cloudflare Turnstile or equivalent challenge verification;
- rate limits by account/session plus coarse network signals;
- one active Ranked race per account;
- replay protection in Redis;
- server-generated opaque session ids;
- suspicious reconnect storms and parallel sessions raise risk.

IP/device signals are supporting evidence only because VPNs, shared networks and privacy tools are legitimate.

## Failure behavior

Anti-cheat must fail safely for competitive integrity without unnecessarily breaking Casual:

- Redis anti-cheat unavailable: new Ranked starts are temporarily blocked; Casual remains available;
- PostgreSQL result persistence unavailable: completed Ranked result remains provisional/retryable and does not mutate leaderboard;
- telemetry batch lost: reconnect/resume can continue from the last server-accepted sequence; missing coverage can move the race to `review` but should not ban the user;
- verifier exception: status remains `provisional`, never auto-verifies by exception;
- client telemetry unsupported: Casual allowed, Ranked unavailable until compatible client is used.

## Components

Planned boundaries:

- `domain/anti_cheat.py`: telemetry types, deterministic feature extraction, risk/reason model, verification decision;
- `domain/race_protocol.py`: strict parsing of challenge-bound telemetry batches;
- `services/anti_cheat.py`: active Redis-backed evidence accumulation and final verification orchestration;
- `services/races.py`: completion emits provisional durable result; no direct trust of client metrics;
- `infrastructure/redis_anti_cheat.py`: challenge/replay/rolling evidence state;
- `infrastructure/postgres_results.py`: verification columns and idempotent status updates;
- `api/race_routes.py`: Ranked challenge delivery and telemetry WebSocket handling;
- web race input: capture only race-focused gameplay telemetry, batch and send it with progress.

## Testing strategy

Unit tests must cover:

- valid challenge binding and start deadline;
- nonce replay;
- sequence replay/out-of-order batches;
- paste advancing Ranked text;
- inserted text/target mismatch;
- impossible progress/event mismatch;
- normal varied human-like timing -> low risk;
- fast but varied timing -> not automatically invalid;
- perfectly periodic scripted timing -> elevated risk;
- sparse/missing telemetry -> review rather than ban;
- Free/Casual path unaffected;
- Top-1000 prestige requires verified leaderboard position.

Integration tests must cover:

- WebSocket challenge + telemetry happy path;
- invalid challenge produces no leaderboard/MMR mutation;
- result transitions provisional -> verified/review/invalid idempotently;
- Redis restart/reconnect replay safety;
- PostgreSQL stores a bounded trace, not one row per key;
- multiple API workers observe the same challenge/replay state through Redis.

Load tests before public Ranked launch must measure:

- 100 / 500 / 1000 concurrent players;
- approximately 10 telemetry/progress batches per player per second;
- Redis ops/sec and memory;
- API CPU/event-loop lag;
- outgoing snapshot bandwidth;
- p50/p95/p99 progress acknowledgement latency;
- verifier throughput at race completion bursts.

## Rollout

1. In staging/closed beta only, ship telemetry collection and scoring in shadow mode while results are not treated as an official public leaderboard.
2. Inspect distributions from real testers and calibrate thresholds.
3. Before public Ranked launch, enable `provisional -> verified/review/invalid` gating for all official MMR/leaderboard mutations.
4. Enable Top-1000 high-assurance gate before public Top-1000 prestige is awarded.
5. Only after enough evidence, consider account-level sanctions for repeated confirmed abuse; sanctions are explicitly outside the initial implementation.

## Security invariants

- Client cannot set its own verification status or risk score.
- Client cannot directly submit a leaderboard position.
- Authoritative confirmed progress is derived from accepted race-field input against the server target, not from client offset alone.
- High CPM alone never bans or invalidates a race.
- Pro subscription never weakens anti-cheat requirements.
- No Ranked result affects MMR or Top-1000 before server verification.
- No raw database/token/anti-cheat secrets are committed to Git.
- Anti-cheat captures gameplay input only, never global keyboard activity.
