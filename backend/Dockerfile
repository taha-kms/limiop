FROM python:3.14.7-slim-bookworm@sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52 AS builder

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN python -m venv /opt/venv

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m pip install --no-cache-dir .

FROM python:3.14.7-slim-bookworm@sha256:23c59390fc717bf09f9336908199a0ae75d9c4264bf296123f94ad772fea3b52 AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 skillsync \
    && useradd --uid 10001 --gid skillsync --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin skillsync

WORKDIR /app

COPY --from=builder /opt/venv /opt/venv
COPY --chown=skillsync:skillsync alembic.ini ./
COPY --chown=skillsync:skillsync alembic ./alembic

USER skillsync

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
