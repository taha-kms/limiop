FROM python:3.13.16-slim-bookworm@sha256:a1165e272e578941b84abc79e4ab38a0305cd12803a5c4247979ac7655f4d641

ENV AIRFLOW_HOME=/opt/airflow \
    PATH="/opt/venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN python -m venv /opt/venv \
    && groupadd --gid 50000 airflow \
    && useradd --uid 50000 --gid airflow --create-home --home-dir /home/airflow airflow

WORKDIR /app/airflow

COPY platform/db/pyproject.toml /app/platform/db/pyproject.toml
COPY platform/db/platform_db /app/platform/db/platform_db
COPY platform/skills/pyproject.toml /app/platform/skills/pyproject.toml
COPY platform/skills/platform_skills /app/platform/skills/platform_skills
COPY services/job-ingestion-service/pyproject.toml /app/services/job-ingestion-service/pyproject.toml
COPY services/job-ingestion-service/job_ingestion /app/services/job-ingestion-service/job_ingestion
COPY airflow/requirements.txt ./requirements.txt

RUN python -m pip install --no-cache-dir -e ../platform/db \
    && python -m pip install --no-cache-dir -e ../platform/skills \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY airflow/bootstrap.py ./bootstrap.py
COPY airflow/dags /opt/airflow/dags

RUN chown -R airflow:airflow /opt/airflow /app

USER airflow

CMD ["airflow", "scheduler"]
