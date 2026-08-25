FROM python:3.13.15-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1 AS builder

ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN python -m venv /opt/venv

COPY platform/db/pyproject.toml ./platform/db/pyproject.toml
COPY platform/db/platform_db ./platform/db/platform_db
COPY backend/pyproject.toml backend/README.md ./backend/
COPY backend/app ./backend/app

RUN python -m pip install --no-cache-dir ./platform/db \
    && python -m pip install --no-cache-dir ./backend

FROM python:3.13.15-slim-bookworm@sha256:00faa2debb87529f9f0764e9491d8ba400a3678976616c3bd7cb193745ac20d1 AS runtime

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN groupadd --gid 10001 skillsync \
    && useradd --uid 10001 --gid skillsync --no-create-home --home-dir /nonexistent \
        --shell /usr/sbin/nologin skillsync

WORKDIR /app

RUN install -d -o skillsync -g skillsync -m 0700 /app/uploads/cvs

COPY --from=builder /opt/venv /opt/venv
COPY --chown=skillsync:skillsync backend/alembic.ini ./
COPY --chown=skillsync:skillsync backend/alembic ./alembic

USER skillsync

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
