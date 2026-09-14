from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_api_container_uses_multiple_workers_and_connection_guard():
    dockerfile = (ROOT / 'apps/api/Dockerfile').read_text(encoding='utf-8')

    assert 'WEB_CONCURRENCY' in dockerfile
    assert '--workers' in dockerfile
    assert 'UVICORN_LIMIT_CONCURRENCY' in dockerfile
    assert '--limit-concurrency' in dockerfile


def test_compose_runs_api_against_persistent_postgres_and_redis():
    compose = (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')

    assert '  api:' in compose
    assert 'REDIS_URL:' in compose
    assert 'DATABASE_URL:' in compose
    assert 'WEB_CONCURRENCY:' in compose
    assert 'UVICORN_LIMIT_CONCURRENCY:' in compose
