# BukvoGon MVP Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the first testable BukvoGon vertical slice: Free/Pro entitlement rules, Ranked eligibility, deterministic multiplayer rating updates, Russian typing validation, a FastAPI surface for those rules, and a minimal web shell that exposes Casual and the Ranked paywall.

**Architecture:** Start domain-first in `apps/api`, keeping payment/provider concerns behind entitlement state. Add the web shell only after backend contracts exist. The realtime race engine is not implemented in this slice; its domain interfaces are prepared without introducing unverified infrastructure complexity.

**Tech Stack:** Python 3.12+, FastAPI, Pydantic, Pytest; Next.js + TypeScript for the web shell; GitHub Actions for verification.

**Spec:** `docs/superpowers/specs/2026-09-14-bukvogon-product-design.md`

## Global Constraints

- Free users have unlimited Casual access.
- Pro costs 300 ₽/month at product level.
- Ranked and official leaderboard require an active Pro entitlement.
- No paid mechanic may alter typing speed, accuracy rules, race progress, or rating formula.
- Ranked uses strict `е/ё`; Casual can normalize `е/ё`.
- Server-side domain code owns eligibility and score/rating decisions.

---

### Task 1: Backend project and entitlement domain

**Files:**
- Create: `apps/api/pyproject.toml`
- Create: `apps/api/bukvogon/__init__.py`
- Create: `apps/api/bukvogon/domain/entitlements.py`
- Test: `apps/api/tests/test_entitlements.py`

**Interfaces:**
- Produces: `EntitlementStatus`, `Entitlement`, `can_play_ranked(entitlement) -> bool`, `can_view_leaderboard(entitlement) -> bool`.

- [ ] Write tests proving `FREE` and `PRO_EXPIRED` cannot use Ranked, while `PRO_ACTIVE` can.
- [ ] Run `pytest tests/test_entitlements.py -q` and confirm the tests fail because the production module does not exist.
- [ ] Implement the minimal entitlement domain.
- [ ] Run the test again and require a green result.
- [ ] Commit as `feat(api): add subscription entitlements`.

### Task 2: Russian typing rules and metrics

**Files:**
- Create: `apps/api/bukvogon/domain/typing.py`
- Test: `apps/api/tests/test_typing.py`

**Interfaces:**
- Produces: `TypingMode`, `normalize_character`, `validate_typed_prefix`, `TypingMetrics`, `calculate_metrics`.

- [ ] Write failing tests for Casual `е/ё` normalization, Ranked strictness, prefix validation, CPM/WPM/accuracy calculations.
- [ ] Run tests and confirm correct red failures.
- [ ] Implement minimal pure functions.
- [ ] Run all backend tests and require green.
- [ ] Commit as `feat(api): add russian typing rules`.

### Task 3: Ranked eligibility and rating engine

**Files:**
- Create: `apps/api/bukvogon/domain/ranked.py`
- Test: `apps/api/tests/test_ranked.py`

**Interfaces:**
- Consumes: entitlement domain.
- Produces: `RankedEligibility`, `check_ranked_eligibility`, `RankedPlayer`, `RankedResult`, `MultiplayerEloEngine.rate`.

- [ ] Write failing tests for Free rejection, active-Pro acceptance, deterministic ordering, zero-sum-ish rating movement, first-place gain, last-place loss, and stable handling of ties.
- [ ] Run tests and confirm red.
- [ ] Implement a deterministic multiplayer Elo engine by pairwise expected-score aggregation; keep K configurable.
- [ ] Run all backend tests and require green.
- [ ] Commit as `feat(api): add ranked eligibility and rating`.

### Task 4: FastAPI contract slice

**Files:**
- Create: `apps/api/bukvogon/main.py`
- Create: `apps/api/bukvogon/api/models.py`
- Create: `apps/api/bukvogon/api/routes.py`
- Test: `apps/api/tests/test_api.py`

**Interfaces:**
- `GET /health`
- `GET /v1/access/{status}` returns Casual/Ranked/leaderboard capabilities.
- `POST /v1/typing/validate` validates a typed prefix under Casual/Ranked rules.
- `POST /v1/ranked/rate` computes rating changes for a supplied ordered result; endpoint is development-only contract scaffolding and not a production trust boundary.

- [ ] Write failing API tests with `TestClient`.
- [ ] Run tests and confirm red.
- [ ] Implement routes backed only by domain functions.
- [ ] Run all backend tests and require green.
- [ ] Commit as `feat(api): expose mvp domain contracts`.

### Task 5: Web product shell

**Files:**
- Create: `apps/web/package.json`
- Create: `apps/web/tsconfig.json`
- Create: `apps/web/next.config.ts`
- Create: `apps/web/app/layout.tsx`
- Create: `apps/web/app/page.tsx`
- Create: `apps/web/app/globals.css`
- Create: `apps/web/app/ranked/page.tsx`
- Create: `apps/web/lib/access.ts`
- Test: `apps/web/lib/access.test.ts`

**Interfaces:**
- Produces: `AccessStatus`, `canPlayRanked`, `getRankedCta`.

- [ ] Write failing Vitest tests for Free and Pro Ranked CTA/access logic.
- [ ] Run test and confirm red.
- [ ] Implement access helper and minimal premium-aware landing UI.
- [ ] Run Vitest and Next.js build.
- [ ] Commit as `feat(web): add free and pro product shell`.

### Task 6: Repository verification and CI

**Files:**
- Create: `.gitignore`
- Create: `.github/workflows/ci.yml`
- Create: `docker-compose.yml`
- Update: `README.md`

**Interfaces:**
- CI verifies backend tests and web test/build independently.

- [ ] Add Python and Node dependency install steps.
- [ ] Run backend test suite.
- [ ] Run web test suite.
- [ ] Run web production build.
- [ ] Open a PR from `feat/mvp-foundation` to `main` and use GitHub Actions as remote verification evidence.
- [ ] Only after green CI describe the slice as passing.
