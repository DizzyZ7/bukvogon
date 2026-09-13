export type RaceVisualThemeId = 'cars' | 'cats' | 'caterpillars' | 'planes';

export type RaceVisualTheme = Readonly<{
  id: RaceVisualThemeId;
  label: string;
  description: string;
  icon: string;
  variantCount: number;
}>;

export type RaceVisualThemeStorage = Pick<Storage, 'getItem' | 'setItem'>;

export const RACE_VISUAL_THEME_STORAGE_KEY = 'bukvogon:race-visual-theme:v1';
export const DEFAULT_RACE_VISUAL_THEME: RaceVisualThemeId = 'cars';

export const RACE_VISUAL_THEMES: readonly RaceVisualTheme[] = [
  {
    id: 'cars',
    label: 'Машинки',
    description: 'Классическая гонка: разные цвета и ливреи.',
    icon: '🏎️',
    variantCount: 4,
  },
  {
    id: 'cats',
    label: 'Котики',
    description: 'Все участники бегут котиками разных окрасов.',
    icon: '🐈',
    variantCount: 4,
  },
  {
    id: 'caterpillars',
    label: 'Гусенички',
    description: 'Мягкая гонка цветных гусеничек по дорожкам.',
    icon: '🐛',
    variantCount: 4,
  },
  {
    id: 'planes',
    label: 'Самолеты',
    description: 'Воздушная гонка с разными ливреями самолетов.',
    icon: '✈️',
    variantCount: 4,
  },
] as const;

const THEMES_BY_ID = new Map<RaceVisualThemeId, RaceVisualTheme>(
  RACE_VISUAL_THEMES.map((theme) => [theme.id, theme] as const),
);

export function normalizeRaceVisualTheme(value: string | null | undefined): RaceVisualThemeId {
  return RACE_VISUAL_THEMES.some((theme) => theme.id === value)
    ? (value as RaceVisualThemeId)
    : DEFAULT_RACE_VISUAL_THEME;
}

export function getRaceVisualTheme(themeId: RaceVisualThemeId): RaceVisualTheme {
  return THEMES_BY_ID.get(themeId) ?? THEMES_BY_ID.get(DEFAULT_RACE_VISUAL_THEME)!;
}

export function getRaceVariant(themeId: RaceVisualThemeId, participantIndex: number): number {
  const count = getRaceVisualTheme(themeId).variantCount;
  const index = Number.isFinite(participantIndex) ? Math.trunc(participantIndex) : 0;
  return ((index % count) + count) % count;
}

export function readRaceVisualTheme(storage: RaceVisualThemeStorage): RaceVisualThemeId {
  return normalizeRaceVisualTheme(storage.getItem(RACE_VISUAL_THEME_STORAGE_KEY));
}

export function writeRaceVisualTheme(
  storage: RaceVisualThemeStorage,
  themeId: RaceVisualThemeId,
): void {
  storage.setItem(RACE_VISUAL_THEME_STORAGE_KEY, normalizeRaceVisualTheme(themeId));
}
