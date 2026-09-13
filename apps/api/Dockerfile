FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    WEB_CONCURRENCY=2 \
    UVICORN_LIMIT_CONCURRENCY=1000

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY bukvogon /app/bukvogon

RUN python -m pip install --no-cache-dir . \
    && useradd --create-home --uid 10001 bukvogon \
    && chown -R bukvogon:bukvogon /app

USER bukvogon

EXPOSE 8000

CMD ["sh", "-c", "exec uvicorn bukvogon.main:app --host 0.0.0.0 --port 8000 --workers ${WEB_CONCURRENCY} --limit-concurrency ${UVICORN_LIMIT_CONCURRENCY} --timeout-keep-alive 5"]
