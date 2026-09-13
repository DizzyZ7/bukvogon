export type RaceRankId =
  | 'novice'
  | 'bronze'
  | 'silver'
  | 'gold'
  | 'platinum'
  | 'diamond'
  | 'master'
  | 'grandmaster';

export type RaceSubscription = 'free' | 'pro';

export type RacePrestige = Readonly<{
  subscription: RaceSubscription;
  rank?: RaceRankId | null;
  leaderboardPosition?: number | null;
}>;

export type PrestigePresentation = Readonly<{
  showAura: boolean;
  showCrown: boolean;
  auraClassName: string;
  badgeClassName: string;
  badgeLabel: string;
}>;

const RANK_LABELS: Record<RaceRankId, string> = {
  novice: 'Новичок',
  bronze: 'Бронза',
  silver: 'Серебро',
  gold: 'Золото',
  platinum: 'Платина',
  diamond: 'Алмаз',
  master: 'Мастер',
  grandmaster: 'Грандмастер',
};

export function getRankLabel(rank: RaceRankId): string {
  return RANK_LABELS[rank];
}

export function isTop1000(position?: number | null): boolean {
  if (position == null || !Number.isInteger(position)) return false;
  return position >= 1 && position <= 1000;
}

export function getPrestigePresentation(prestige: RacePrestige): PrestigePresentation {
  if (prestige.subscription !== 'pro') {
    return {
      showAura: false,
      showCrown: false,
      auraClassName: 'racePrestigeAura racePrestigeAura--none',
      badgeClassName: 'racePrestigeBadge racePrestigeBadge--free',
      badgeLabel: 'Free',
    };
  }

  const rank = prestige.rank ?? 'novice';

  if (isTop1000(prestige.leaderboardPosition)) {
    return {
      showAura: true,
      showCrown: true,
      auraClassName: 'racePrestigeAura racePrestigeAura--top1000',
      badgeClassName: 'racePrestigeBadge racePrestigeBadge--top1000',
      badgeLabel: `#${prestige.leaderboardPosition} · ${getRankLabel(rank)}`,
    };
  }

  return {
    showAura: true,
    showCrown: false,
    auraClassName: `racePrestigeAura racePrestigeAura--${rank}`,
    badgeClassName: `racePrestigeBadge racePrestigeBadge--${rank}`,
    badgeLabel: getRankLabel(rank),
  };
}
