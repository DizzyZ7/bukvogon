# Database Disaster Recovery Design

## Goal

Keep BukvoGon PostgreSQL data durable during normal container lifecycle and automatically create a full encrypted backup at least once per week, delivering the entire backup to the owner's private Telegram chat in restorable parts.

## Primary durability

PostgreSQL data lives on a named Docker volume (`pgdata`). Recreating the database container must not recreate the database storage.

Redis uses a separate named volume and AOF persistence for hot race state, but Redis is not treated as the permanent system of record.

## Weekly full backup

A dedicated backup container runs every Sunday at 04:15 UTC.

Backup flow:

1. Run `pg_dump` in PostgreSQL custom format with compression.
2. Validate the dump with `pg_restore --list` before considering it usable.
3. Encrypt the complete dump using `age` passphrase encryption. The passphrase is supplied only through `BACKUP_PASSPHRASE` and never committed.
4. Calculate SHA-256 for the encrypted archive.
5. Split the encrypted archive into 45 MiB pieces. This stays below the official Telegram Bot API 50 MB upload limit while still allowing the complete database to be delivered through Telegram.
6. Generate a manifest containing timestamp, encrypted archive checksum, ordered part names and per-part checksums.
7. Send the manifest and every part sequentially to `TELEGRAM_CHAT_ID` using `TELEGRAM_BOT_TOKEN`.
8. Keep a local copy on a named `backups` volume for 35 days.
9. Remove older backup generations only after a new backup has been validated.

## Telegram behavior

The backup bot must send only to the configured private chat id. The bot token and chat id live in environment/secrets, never source control.

Every weekly delivery begins with a summary message and includes all encrypted parts plus the manifest. A partial Telegram delivery is considered a backup-delivery failure and must result in a failure notification attempt and a non-zero job exit code.

## Restore procedure

A restore script:

1. verifies every part against the manifest;
2. concatenates parts in order;
3. verifies the full encrypted archive SHA-256;
4. decrypts it using `BACKUP_PASSPHRASE`;
5. validates the dump via `pg_restore --list`;
6. restores with `pg_restore` into an explicitly supplied target database.

Restore never runs automatically on production.

## Secrets

Required environment variables:

- `POSTGRES_DB`
- `POSTGRES_USER`
- `POSTGRES_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`
- `BACKUP_PASSPHRASE`

The repository contains only `.env.example` placeholders.

## Failure handling

- `pg_dump` failure: do not encrypt or send an invalid file.
- dump validation failure: abort and keep previous backups.
- encryption failure: abort.
- Telegram API failure: retry each upload with bounded retries; keep local encrypted backup even when delivery fails.
- disk-space failure: fail loudly before deleting the most recent known-good backup.

## Security

Raw database dumps are never sent to Telegram. Only passphrase-encrypted backup bytes are transmitted. The passphrase must be stored separately from Telegram and from the repository.

## Testing

Shell/Python helper tests cover manifest generation, chunk ordering, checksum verification and required-env validation. CI validates scripts syntactically; full `pg_dump` restore is intended for container integration tests.