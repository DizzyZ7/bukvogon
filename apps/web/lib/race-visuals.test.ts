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
  it('ships four initial themes in a stable order', () => {
    expect(RACE_VISUAL_THEMES.map((theme) => theme.id)).toEqual([
      'cars',
      'cats',
      'caterpillars',
      'planes',
    ]);
  });

  it('uses cars as the safe fallback', () => {
    expect(DEFAULT_RACE_VISUAL_THEME).toBe('cars');
    expect(normalizeRaceVisualTheme(null)).toBe('cars');
    expect(normalizeRaceVisualTheme('hovercraft')).toBe('cars');
  });

  it('preserves known theme ids', () => {
    expect(normalizeRaceVisualTheme('cats')).toBe('cats');
    expect(normalizeRaceVisualTheme('caterpillars')).toBe('caterpillars');
    expect(normalizeRaceVisualTheme('planes')).toBe('planes');
  });

  it('wraps visual variants deterministically', () => {
    expect(getRaceVariant('cars', 0)).toBe(0);
    expect(getRaceVariant('cars', 3)).toBe(3);
    expect(getRaceVariant('cars', 4)).toBe(0);
    expect(getRaceVariant('cats', 9)).toBe(1);
  });

  it('persists and restores a valid selected theme', () => {
    const values = new Map<string, string>();
    const storage = {
      getItem: (key: string) => values.get(key) ?? null,
      setItem: (key: string, value: string) => {
        values.set(key, value);
      },
    };

    writeRaceVisualTheme(storage, 'cats');
    expect(readRaceVisualTheme(storage)).toBe('cats');
  });

  it('falls back when stored data contains an unknown theme', () => {
    const storage = {
      getItem: () => 'spaceships',
      setItem: () => undefined,
    };

    expect(readRaceVisualTheme(storage)).toBe('cars');
  });
});
