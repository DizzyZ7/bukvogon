# БуквоГон

Русскоязычная соревновательная браузерная typing-race игра. Скорость игрового объекта определяется скоростью и точностью печати.

## Free

Неограниченные Casual-гонки, комнаты с друзьями, тренировка, боты, XP, достижения, гараж и базовая статистика.

## Pro — 300 ₽/мес

Ranked matchmaking, MMR и дивизионы, официальный лидерборд, история рейтинга, расширенная аналитика, ранговые визуальные эффекты и сезонные косметические награды.

Подписка не влияет на скорость, точность, сложность текста или формулу рейтинга. БуквоГон принципиально не pay-to-win.

## Архитектура

```text
apps/
  api/    FastAPI + WebSocket + Redis + PostgreSQL
  web/    Next.js + TypeScript
ops/
  backup/ weekly PostgreSQL disaster-recovery backup

docs/
  superpowers/specs/
  superpowers/plans/
```

### Realtime

- до 6 игроков в первой версии одной гонки;
- клиент отправляет компактный progress event, а не пишет каждый символ в PostgreSQL;
- полезная частота progress event ограничена примерно 10–12 событиями/сек на игрока;
- сообщения WebSocket ограничены 2 KiB и имеют строгий whitelist полей;
- активное состояние гонки находится в Redis с TTL 20 минут;
- Redis mutation lock защищает race state при нескольких API worker-ах;
- Redis pub/sub синхронизирует WebSocket-клиентов между процессами;
- PostgreSQL получает долговечную запись только при финише игрока;
- запись результата выполняется после освобождения race lock.

### Persistent storage

`docker-compose.yml` использует именованные volumes:

- `pgdata` — постоянные данные PostgreSQL;
- `redisdata` — Redis AOF для активных сессий;
- `backups` — локальные поколения зашифрованных backup-файлов.

Redis запущен с `appendonly yes` и `appendfsync everysec`.

## Backend

```bash
cd apps/api
python -m venv .venv
python -m pip install -e '.[dev]'
python -m pytest
uvicorn bukvogon.main:app --reload
```

Основные realtime endpoints:

```text
POST /v1/races
GET  /v1/races/{race_id}
WS   /v1/races/{race_id}/ws/{player_id}
```

## Web

```bash
cd apps/web
npm install
npm run dev
```

## Docker deployment

Создай локальный `.env` из примера и замени все production secrets:

```bash
cp .env.example .env
docker compose up -d --build
```

API container по умолчанию запускает 2 Uvicorn worker-а, каждый с ограничением concurrency. Значения можно менять через `WEB_CONCURRENCY` и `UVICORN_LIMIT_CONCURRENCY` после нагрузочного тестирования на реальном сервере.

## Еженедельный backup PostgreSQL в Telegram

Backup container запускает полный backup каждое воскресенье в `04:15 UTC`.

Пайплайн:

```text
pg_dump (custom/compressed)
 -> pg_restore --list validation
 -> age recipient encryption
 -> SHA-256
 -> части по 45 MiB
 -> manifest + checksums
 -> Telegram private chat
 -> local encrypted retention 35 days
```

Незашифрованный dump в Telegram никогда не отправляется.

### 1. Создать отдельный age-ключ

Делай это НЕ на production-сервере:

```bash
age-keygen -o bukvogon-backup-key.txt
```

`age-keygen` выведет публичный recipient вида `age1...`. Только этот публичный recipient добавь в `.env`:

```text
BACKUP_AGE_RECIPIENT=age1...
```

Файл `bukvogon-backup-key.txt` — приватный ключ восстановления. Не коммить его и по возможности вообще не копируй на production-сервер.

### 2. Telegram

В `.env` должны быть заполнены:

```text
TELEGRAM_BOT_TOKEN=...
TELEGRAM_CHAT_ID=...
```

Backup bot отправляет manifest, файл checksums и все части полного зашифрованного dump последовательно. Если Telegram delivery завершается не полностью, job выходит с ошибкой и не удаляет локальное поколение backup.

### 3. Ручная проверка backup

После настройки secrets можно запустить вне расписания:

```bash
docker compose run --rm backup /opt/bukvogon/backup.sh
```

### 4. Restore

Restore никогда не запускается автоматически. Перед ним нужен приватный age identity и явное подтверждение `RESTORE_CONFIRM=YES`.

Пример общей схемы:

```bash
BACKUP_AGE_IDENTITY_FILE=/secure/bukvogon-backup-key.txt \
RESTORE_POSTGRES_HOST=postgres \
RESTORE_POSTGRES_DB=bukvogon \
RESTORE_POSTGRES_USER=bukvogon \
RESTORE_POSTGRES_PASSWORD='...' \
RESTORE_CONFIRM=YES \
/opt/bukvogon/restore.sh /backups/<generation>/bukvogon-<timestamp>.manifest.txt
```

Restore сначала проверяет SHA-256 каждой части, собирает полный encrypted archive, проверяет его общий SHA-256, расшифровывает через `age`, валидирует `pg_restore --list` и только затем восстанавливает БД.

## Документация

- `docs/superpowers/specs/2026-09-14-bukvogon-product-design.md`
- `docs/superpowers/specs/2026-09-14-race-visual-themes-design.md`
- `docs/superpowers/specs/2026-09-14-realtime-session-design.md`
- `docs/superpowers/specs/2026-09-14-database-disaster-recovery-design.md`
- `docs/superpowers/plans/2026-09-14-mvp-foundation.md`
