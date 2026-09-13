# БуквоГон

Русскоязычная соревновательная браузерная игра, где скорость машины определяется скоростью и точностью печати.

## Free

Неограниченные Casual-гонки, комнаты с друзьями, тренировка, боты, XP, достижения, гараж и базовая статистика.

## Pro — 300 ₽/мес

Ranked matchmaking, MMR и дивизионы, официальный лидерборд, история рейтинга, расширенная аналитика и сезонные косметические награды.

Подписка не влияет на скорость, точность, сложность текста или формулу рейтинга. БуквоГон принципиально не pay-to-win.

## Архитектура

```text
apps/
  api/    FastAPI и доменная логика
  web/    Next.js + TypeScript

docs/
  superpowers/specs/
  superpowers/plans/
```

## Backend

```bash
cd apps/api
python -m venv .venv
python -m pip install -e '.[dev]'
python -m pytest
uvicorn bukvogon.main:app --reload
```

## Web

```bash
cd apps/web
npm install
npm run dev
```

## Dev services

```bash
docker compose up -d
```

## Документация

- `docs/superpowers/specs/2026-09-14-bukvogon-product-design.md`
- `docs/superpowers/plans/2026-09-14-mvp-foundation.md`
