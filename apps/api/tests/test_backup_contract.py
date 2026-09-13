from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_compose_persists_postgres_redis_and_has_backup_service():
    compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')

    assert 'pgdata:/var/lib/postgresql/data' in compose
    assert 'redisdata:/data' in compose
    assert '--appendonly yes' in compose
    assert '--appendfsync everysec' in compose
    assert 'backup:' in compose
    assert 'backups:/backups' in compose


def test_backup_container_runs_weekly_and_encrypts_before_telegram_delivery():
    dockerfile = (ROOT / 'ops/backup/Dockerfile').read_text(encoding='utf-8')
    crontab = (ROOT / 'ops/backup/crontab').read_text(encoding='utf-8')
    script = (ROOT / 'ops/backup/backup.sh').read_text(encoding='utf-8')

    assert 'apk add --no-cache' in dockerfile
    assert 'age' in dockerfile
    assert '15 4 * * 0' in crontab
    assert 'pg_dump' in script
    assert 'pg_restore --list' in script
    assert 'age -r "$BACKUP_AGE_RECIPIENT"' in script
    assert 'split -b 45m' in script
    assert 'sendDocument' in script
    assert 'sha256sum' in script


def test_restore_verifies_parts_and_requires_age_identity_file():
    restore = (ROOT / 'ops/backup/restore.sh').read_text(encoding='utf-8')

    assert 'sha256sum -c' in restore
    assert 'age --decrypt -i "$BACKUP_AGE_IDENTITY_FILE"' in restore
    assert 'pg_restore --list' in restore
    assert 'pg_restore' in restore


def test_env_example_contains_placeholders_not_real_secrets():
    env_example = (ROOT / '.env.example').read_text(encoding='utf-8')

    assert 'TELEGRAM_BOT_TOKEN=' in env_example
    assert 'TELEGRAM_CHAT_ID=' in env_example
    assert 'BACKUP_AGE_RECIPIENT=' in env_example
    assert 'AGE-SECRET-KEY-' not in env_example
