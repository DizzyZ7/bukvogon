import { describe, expect, it } from 'vitest';

import {
  getPrestigePresentation,
  getRankLabel,
  isTop1000,
  type RaceRankId,
} from './race-prestige';

const ranks: RaceRankId[] = [
  'novice',
  'bronze',
  'silver',
  'gold',
  'platinum',
  'diamond',
  'master',
  'grandmaster',
];

describe('race prestige', () => {
  it('keeps free players without premium effects', () => {
    const result = getPrestigePresentation({ subscription: 'free' });

    expect(result.showAura).toBe(false);
    expect(result.showCrown).toBe(false);
    expect(result.badgeLabel).toBe('Free');
  });

  it('maps every ranked division to a stable readable label', () => {
    expect(ranks.map(getRankLabel)).toEqual([
      'Новичок',
      'Бронза',
      'Серебро',
      'Золото',
      'Платина',
      'Алмаз',
      'Мастер',
      'Грандмастер',
    ]);
  });

  it('gives pro players rank-based neon prestige', () => {
    const result = getPrestigePresentation({
      subscription: 'pro',
      rank: 'diamond',
      leaderboardPosition: 1842,
    });

    expect(result.showAura).toBe(true);
    expect(result.showCrown).toBe(false);
    expect(result.auraClassName).toContain('racePrestigeAura--diamond');
    expect(result.badgeLabel).toBe('Алмаз');
  });

  it('derives top 1000 from leaderboard position', () => {
    expect(isTop1000(1)).toBe(true);
    expect(isTop1000(1000)).toBe(true);
    expect(isTop1000(1001)).toBe(false);
    expect(isTop1000(null)).toBe(false);
  });

  it('gives top 1000 pro players a golden aura and crown', () => {
    const result = getPrestigePresentation({
      subscription: 'pro',
      rank: 'grandmaster',
      leaderboardPosition: 128,
    });

    expect(result.showAura).toBe(true);
    expect(result.showCrown).toBe(true);
    expect(result.auraClassName).toContain('racePrestigeAura--top1000');
    expect(result.badgeLabel).toBe('#128 · Грандмастер');
  });

  it('does not grant top 1000 visuals to a free account even with a stale position', () => {
    const result = getPrestigePresentation({
      subscription: 'free',
      rank: 'master',
      leaderboardPosition: 300,
    });

    expect(result.showAura).toBe(false);
    expect(result.showCrown).toBe(false);
  });
});
