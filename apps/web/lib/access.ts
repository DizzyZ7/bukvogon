export type AccessStatus = 'free' | 'pro_active' | 'pro_grace' | 'pro_expired';

export type RankedCta = {
  label: string;
  href: '/ranked' | '/pro';
};

export function canPlayRanked(status: AccessStatus): boolean {
  return status === 'pro_active';
}

export function getRankedCta(status: AccessStatus): RankedCta {
  if (canPlayRanked(status)) {
    return { label: 'Играть Ranked', href: '/ranked' };
  }

  return { label: 'Открыть Ranked — 300 ₽/мес', href: '/pro' };
}
