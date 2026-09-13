# Race Visual Themes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add locally selectable Cars, Cats, Caterpillars and Planes themes to the BukvoGon race presentation without changing race state or competitive logic.

**Architecture:** Introduce a typed theme registry and persistence helpers in `apps/web/lib`, then build a client-side `RaceScene` that renders one theme for all visible participants. The renderer consumes only participant progress and variant indexes, so future realtime state can replace the preview data without changing theme behavior.

**Tech Stack:** Next.js 16, React 19, TypeScript 7, Vitest 5, CSS.

**Spec:** `docs/superpowers/specs/2026-09-14-race-visual-themes-design.md`

## Global Constraints

- Theme choice is local presentation state only.
- Cars, Cats, Caterpillars and Planes are available from the first release.
- Every visible participant uses the viewer's selected theme with a distinct deterministic variant.
- Theme choice must not affect typing, progress, score, MMR or matchmaking.
- Invalid persisted theme values must fall back to `cars`.
- Selection must persist in browser localStorage.
- No external image assets are required for this slice.

---

### Task 1: Theme registry and persistence

**Files:**
- Create: `apps/web/lib/race-visuals.test.ts`
- Create: `apps/web/lib/race-visuals.ts`

**Interfaces:**
- Produces: `RaceVisualThemeId`, `RaceVisualTheme`, `RACE_VISUAL_THEMES`, `DEFAULT_RACE_VISUAL_THEME`, `normalizeRaceVisualTheme`, `getRaceVisualTheme`, `getRaceVariant`, `readRaceVisualTheme`, `writeRaceVisualTheme`.

- [ ] **Step 1: Write the failing registry tests**

```ts
import { describe, expect, it } from 'vitest';
import {
  DEFAULT_RACE_VISUAL_THEME,
  RACE_VISUAL_THEMES,
  getRaceVariant,
  normalizeRaceVisualTheme,
  readRaceVisualTheme,
  writeRaceVisualTheme,
} from './race-visuals';

describe('race visual themes', () => {
  it('ships four initial themes', () => {
    expect(RACE_VISUAL_THEMES.map((theme) => theme.id)).toEqual(['cars', 'cats', 'caterpillars', 'planes']);
  });

  it('falls back to cars for unknown values', () => {
    expect(DEFAULT_RACE_VISUAL_THEME).toBe('cars');
    expect(normalizeRaceVisualTheme('hovercraft')).toBe('cars');
  });

  it('wraps variants deterministically', () => {
    expect(getRaceVariant('cars', 0)).toBe(0);
    expect(getRaceVariant('cars', 4)).toBe(0);
  });

  it('persists a valid selected theme', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => values.set(key, value),
    };
    writeRaceVisualTheme(storage, 'cats');
    expect(readRaceVisualTheme(storage)).toBe('cats');
  });
});
```

- [ ] **Step 2: Run `npm test -- race-visuals.test.ts` and require failure because `./race-visuals` does not exist.**
- [ ] **Step 3: Implement the typed registry, safe normalizer, deterministic variant wrapping and storage helpers.**
- [ ] **Step 4: Run the targeted test and require green.**
- [ ] **Step 5: Commit as `feat(web): add race visual theme registry`.**

### Task 2: Race visual renderer and selector

**Files:**
- Create: `apps/web/components/race/RaceVisual.tsx`
- Create: `apps/web/components/race/RaceScene.tsx`
- Create: `apps/web/app/play/page.tsx`
- Modify: `apps/web/app/globals.css`

**Interfaces:**
- `RaceVisual({ theme, variant, label })` renders a cosmetic participant shape.
- `RaceScene` owns only selected visual theme; participant progress remains theme-independent.

- [ ] **Step 1: Add `RaceVisual` with four renderer branches keyed by the registry IDs.**
- [ ] **Step 2: Add `RaceScene` with four deterministic preview racers and a semantic theme selector.**
- [ ] **Step 3: Restore the selected theme from localStorage after mount and persist every user selection.**
- [ ] **Step 4: Add `/play` as the playable preview route linked from the existing landing page.**
- [ ] **Step 5: Add responsive CSS for selector cards, lanes and the four CSS-rendered theme families.**
- [ ] **Step 6: Run `npm test` and `npm run build`; both must pass.**
- [ ] **Step 7: Commit as `feat(web): add selectable race visuals`.**

### Task 3: Remote verification

**Files:**
- Existing: `.github/workflows/ci.yml`

**Interfaces:**
- Existing CI must run web tests and production build on the updated PR head.

- [ ] **Step 1: Push commits to `feat/mvp-foundation`.**
- [ ] **Step 2: Confirm PR #1 triggers CI.**
- [ ] **Step 3: Verify backend tests remain green.**
- [ ] **Step 4: Verify web tests and production build are green.**
- [ ] **Step 5: Report the feature as passing only after both jobs succeed.**
