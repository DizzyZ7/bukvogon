# BukvoGon Race Visual Themes Design

## Goal

Allow every player to choose how the entire race is rendered locally without changing race state, matchmaking, typing rules, progress, results, MMR, or any other competitive data.

## Core rule

Race state and race presentation are separate. The server owns participant identity and progress. The browser maps that state into a local visual theme.

Two players in the same race may therefore see the same participants and progress with different themes at the same time.

## Built-in themes

The first release contains four themes:

- `cars` — compact race cars in distinct liveries/colors.
- `cats` — running cats in distinct coat colors.
- `caterpillars` — caterpillars with distinct body palettes.
- `planes` — small aircraft in distinct liveries.

All themes are cosmetic. No theme has a different hitbox, speed, progress curve, typing behavior, or scoring rule.

## Architecture

`RaceState` remains theme-agnostic. Web presentation uses a typed `RaceVisualTheme` registry. `RaceScene` consumes participant progress plus a selected theme and renders each participant through `RaceVisual`.

Theme selection is stored in browser `localStorage` under a versioned product key. Invalid or removed theme IDs safely fall back to `cars`.

The registry is the extension point for future themes. Adding a theme requires a registry entry and a renderer branch; race domain/server code must not change.

## UX

The `/play` page contains:

1. a clear visual-theme selector;
2. a live preview showing the same race state in the selected theme;
3. four participants with distinct variants inside the selected theme;
4. explanatory copy that the preference affects only the current player's view;
5. persistent selection across reloads.

The selector must be keyboard accessible and expose pressed/selected state through semantic buttons.

## Rendering strategy

The initial renderer uses React + CSS shapes rather than image assets or Canvas. This keeps the first slice lightweight, responsive and easy to theme. A later realtime renderer may move animation to Canvas/PixiJS while preserving the same theme IDs and registry contract.

## Testing

Pure registry and persistence behavior is covered by Vitest:

- exactly the four initial themes are registered;
- `cars` is the fallback/default;
- known theme IDs normalize unchanged;
- invalid IDs normalize to the default;
- variant selection is deterministic and wraps safely;
- browser-storage helpers persist and restore a valid selected theme.

GitHub Actions must also pass the production Next.js build before the feature is considered integrated.