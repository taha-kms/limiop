#!/usr/bin/env bash
# Start the built image against a real PostgreSQL and prove it can serve.
#
# Not a unit test and not a substitute for one. This answers the question the
# suite cannot: whether the thing that ships actually starts. An image can pass
# every test in the repository and still fail here — a missing runtime
# dependency, a file the Dockerfile forgot to copy, a migration that never ran.
set -euo pipefail

readonly IMAGE_REF="${IMAGE_REF:?IMAGE_REF must name the image to test}"
readonly NETWORK="smoke-$$"
readonly DATABASE="smoke-db-$$"
readonly API="smoke-api-$$"
readonly PASSWORD="smoke"
readonly URL="postgresql+psycopg://smoke:${PASSWORD}@${DATABASE}:5432/smoke"

cleanup() {
  docker logs "${API}" 2>&1 | tail -40 || true
  docker rm -f "${API}" "${DATABASE}" >/dev/null 2>&1 || true
  docker network rm "${NETWORK}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker network create "${NETWORK}" >/dev/null
docker run -d --name "${DATABASE}" --network "${NETWORK}" \
  -e POSTGRES_USER=smoke -e POSTGRES_PASSWORD="${PASSWORD}" -e POSTGRES_DB=smoke \
  postgres:17.11-alpine >/dev/null

for _ in $(seq 1 60); do
  if docker exec "${DATABASE}" pg_isready -U smoke -d smoke >/dev/null 2>&1; then break; fi
  sleep 1
done

# Migrations run before the image serves, exactly as the deployment baseline
# requires, and the platform chain runs first because the backend chain has a
# foreign key into what it creates.
docker run --rm --network "${NETWORK}" -e SKILLSYNC_DATABASE_URL="${URL}" \
  "${IMAGE_REF}" alembic -c platform/db/alembic.ini upgrade head
docker run --rm --network "${NETWORK}" -e SKILLSYNC_DATABASE_URL="${URL}" \
  "${IMAGE_REF}" alembic upgrade head

docker run -d --name "${API}" --network "${NETWORK}" -p 18000:8000 \
  -e SKILLSYNC_DATABASE_URL="${URL}" \
  -e SKILLSYNC_ENVIRONMENT=staging \
  -e SKILLSYNC_SESSION_SECRET="a-smoke-test-secret-long-enough-to-sign-with" \
  "${IMAGE_REF}" >/dev/null

for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:18000/health >/dev/null; then break; fi
  sleep 1
done

echo "checking liveness"
curl -sf http://127.0.0.1:18000/health | grep -q '"status":"ok"'

# The one that matters. Liveness only proves the process started; readiness
# proves it reached the database and can write where CVs go.
echo "checking readiness"
ready=$(curl -sf http://127.0.0.1:18000/health/ready)
echo "${ready}"
echo "${ready}" | grep -q '"status":"ready"'

echo "checking the public catalogue answers"
curl -sf 'http://127.0.0.1:18000/jobs?limit=1' | grep -q '"jobs"'

echo "smoke test passed"
