#!/usr/bin/env bash
# Start the built image and prove it can serve.
#
# The counterpart to backend/scripts/smoke_test_image.sh, and it answers the
# same question the unit suite cannot: whether the thing that ships starts. A
# standalone build is a traced subset of the dependency graph, so a module the
# trace missed is invisible until the server is asked to run without the rest
# of node_modules behind it.
#
# No database, deliberately. The page it asks for renders without the API, so
# what this proves is that Node booted, the traced bundle is complete, the
# server bound an address reachable from outside the container, and routing
# and server rendering work.
set -euo pipefail

readonly IMAGE_REF="${IMAGE_REF:?IMAGE_REF must name the image to test}"
readonly API_URL="${SMOKE_API_URL:?SMOKE_API_URL must be the address the image was built with}"
readonly CONTAINER="smoke-frontend-$$"

cleanup() {
  docker logs "${CONTAINER}" 2>&1 | tail -40 || true
  docker rm -f "${CONTAINER}" >/dev/null 2>&1 || true
}
trap cleanup EXIT

docker run -d --name "${CONTAINER}" -p 13000:3000 "${IMAGE_REF}" >/dev/null

for _ in $(seq 1 60); do
  if curl -sf http://127.0.0.1:13000/sign-in >/dev/null; then break; fi
  sleep 1
done

# Reaching this from the host at all is the check that HOSTNAME was set. The
# standalone server defaults to localhost, and a container that binds it
# publishes a port nothing answers on.
echo "checking the server answers from outside the container"
page=$(curl -sf http://127.0.0.1:13000/sign-in)
grep -q "<html" <<<"${page}"

# The build argument is inlined into the client bundle rather than read at
# runtime, so this is the only place it can be checked. An image carrying the
# wrong address is broken for every visitor and works perfectly in every test.
echo "checking the API address was inlined into the client bundle"
docker exec "${CONTAINER}" grep -rq "${API_URL}" /app/.next/static

echo "smoke test passed"
