FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS builder

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN python -m venv /opt/venv

COPY pyproject.toml README.md ./
COPY app ./app

RUN python -m pip install --no-cache-dir .

FROM python:3.12.13-slim-bookworm@sha256:4766d8b510c428e595d74b9cc5bbb2fae8e26316fffb4adc89908d79aacd58a2 AS runtime

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
