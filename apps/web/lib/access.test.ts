import { describe, expect, it } from 'vitest';

import { canPlayRanked, getRankedCta } from './access';

describe('ranked access', () => {
  it('keeps ranked locked for free users', () => {
    expect(canPlayRanked('free')).toBe(false);
    expect(getRankedCta('free')).toEqual({
      label: 'Открыть Ranked — 300 ₽/мес',
      href: '/pro',
    });
  });

  it('opens ranked for active pro users', () => {
    expect(canPlayRanked('pro_active')).toBe(true);
    expect(getRankedCta('pro_active')).toEqual({
      label: 'Играть Ranked',
      href: '/ranked',
    });
  });

  it('locks ranked when pro has expired', () => {
    expect(canPlayRanked('pro_expired')).toBe(false);
  });
});
