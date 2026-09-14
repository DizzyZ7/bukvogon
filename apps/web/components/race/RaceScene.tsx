'use client';

import { useEffect, useState } from 'react';

import {
  getPrestigePresentation,
  type RacePrestige,
} from '../../lib/race-prestige';
import {
  DEFAULT_RACE_VISUAL_THEME,
  RACE_VISUAL_THEMES,
  getRaceVariant,
  getRaceVisualTheme,
  readRaceVisualTheme,
  writeRaceVisualTheme,
  type RaceVisualThemeId,
} from '../../lib/race-visuals';
import { RaceVisual } from './RaceVisual';

type PreviewRacer = Readonly<{
  id: string;
  name: string;
  progress: number;
  cpm: number;
  prestige: RacePrestige;
}>;

const PREVIEW_RACERS: readonly PreviewRacer[] = [
  {
    id: 'you',
    name: 'Ты',
    progress: 76,
    cpm: 412,
    prestige: {
      subscription: 'pro',
      rank: 'grandmaster',
      leaderboardPosition: 128,
    },
  },
  {
    id: 'fox',
    name: 'Лиса',
    progress: 63,
    cpm: 367,
    prestige: {
      subscription: 'pro',
      rank: 'diamond',
      leaderboardPosition: 1842,
    },
  },
  {
    id: 'keyboard',
    name: 'Клавиша',
    progress: 51,
    cpm: 332,
    prestige: {
      subscription: 'pro',
      rank: 'silver',
      leaderboardPosition: 5917,
    },
  },
  {
    id: 'meteor',
    name: 'Метеор',
    progress: 39,
    cpm: 288,
    prestige: {
      subscription: 'free',
    },
  },
] as const;

export function RaceScene() {
  const [selectedTheme, setSelectedTheme] = useState<RaceVisualThemeId>(
    DEFAULT_RACE_VISUAL_THEME,
  );

  useEffect(() => {
    setSelectedTheme(readRaceVisualTheme(window.localStorage));
  }, []);

  const selectTheme = (themeId: RaceVisualThemeId) => {
    setSelectedTheme(themeId);
    writeRaceVisualTheme(window.localStorage, themeId);
  };

  const theme = getRaceVisualTheme(selectedTheme);

  return (
    <section className="raceExperience" aria-labelledby="race-preview-title">
      <div className="raceExperience__top">
        <div>
          <div className="eyebrow">ВИЗУАЛ ГОНКИ</div>
          <h2 id="race-preview-title">Одна гонка. Твой способ ее видеть.</h2>
          <p className="muted raceExperience__copy">
            Выбор сохраняется только у тебя. Другой участник этой же гонки может одновременно видеть всех котиками или самолетами.
          </p>
        </div>
        <div className="raceExperience__badge">Только твой экран</div>
      </div>

      <div className="themePicker" role="group" aria-label="Выбор визуальной темы гонки">
        {RACE_VISUAL_THEMES.map((item) => {
          const isSelected = item.id === selectedTheme;
          return (
            <button
              className={`themeCard${isSelected ? ' themeCard--selected' : ''}`}
              type="button"
              key={item.id}
              aria-pressed={isSelected}
              onClick={() => selectTheme(item.id)}
            >
              <span className="themeCard__icon" aria-hidden="true">{item.icon}</span>
              <span className="themeCard__body">
                <strong>{item.label}</strong>
                <small>{item.description}</small>
              </span>
              <span className="themeCard__state" aria-hidden="true">{isSelected ? '✓' : '↗'}</span>
            </button>
          );
        })}
      </div>

      <div className={`raceBoard raceBoard--${selectedTheme}`}>
        <div className="raceBoard__header">
          <div>
            <span className="label">ПРЕВЬЮ</span>
            <strong>{theme.label}</strong>
          </div>
          <span>Одинаковый race state · разный renderer</span>
        </div>

        <div className="raceLanes">
          {PREVIEW_RACERS.map((racer, index) => {
            const progress = Math.max(4, Math.min(94, racer.progress));
            const prestige = getPrestigePresentation(racer.prestige);
            const isPro = racer.prestige.subscription === 'pro';

            return (
              <div className="raceLanePreview" key={racer.id}>
                <div className="raceLanePreview__meta">
                  <div className="raceLanePreview__identity">
                    <strong>{racer.name}</strong>
                    {isPro && (
                      <span className={prestige.badgeClassName}>
                        {prestige.badgeLabel}
                      </span>
                    )}
                  </div>
                  <span>{racer.cpm} зн/мин</span>
                </div>
                <div className="raceLanePreview__rail">
                  <div className="raceLanePreview__start" aria-hidden="true">СТАРТ</div>
                  <div className="raceLanePreview__finish" aria-hidden="true">
                    <i /><i /><i /><i /><i /><i />
                  </div>
                  <div
                    className={`raceRunner${prestige.showCrown ? ' raceRunner--top1000' : ''}`}
                    style={{ left: `${progress}%` }}
                    title={`${racer.name}: ${racer.progress}%`}
                  >
                    {prestige.showAura && (
                      <span className={prestige.auraClassName} aria-hidden="true" />
                    )}
                    {prestige.showCrown && (
                      <span className="racePrestigeCrown" aria-hidden="true">♛</span>
                    )}
                    <RaceVisual
                      theme={selectedTheme}
                      variant={getRaceVariant(selectedTheme, index)}
                      label={`${racer.name}, ${theme.label}, ${racer.progress}% дистанции, ${prestige.badgeLabel}`}
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
