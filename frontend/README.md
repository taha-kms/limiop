# SkillSync frontend

The Next.js application that serves the job catalogue.

## Requirements

Node.js 20.9 or later. Next.js 16 dropped support for Node 18.

## Running it

```bash
npm install
npm run dev
```

The development server listens on <http://localhost:3000>. It expects the API
to be reachable; see the backend setup guide for starting that.

## Configuration

Two variables, neither of them a secret. The catalogue API is public and
unauthenticated, so these are addresses rather than credentials.

| Variable              | Read by     | Default                             |
| --------------------- | ----------- | ----------------------------------- |
| `NEXT_PUBLIC_API_URL` | The browser | `http://localhost:8000`             |
| `SKILLSYNC_API_URL`   | The server  | Falls back to `NEXT_PUBLIC_API_URL` |

There are two because the browser and the server do not always reach the API at
the same address. Inside Compose the server uses the service name while the
browser uses a published port, and no single value is correct for both.

`NEXT_PUBLIC_API_URL` is inlined at build time, so a container image is built
for the address it will be served from.

## Checks

```bash
npm run format:check   # Prettier
npm run lint           # ESLint
npm run typecheck      # Route type generation, then tsc
npm run test           # Vitest
npm run build          # Production build
npm run test:e2e       # Playwright, against a running stack
```

CI runs all six, the browser test in its own job. `npm run typecheck` regenerates the route types first,
because Next derives `PageProps` and `LayoutProps` from the files on disk and
stale types would hide a broken route.

## The browser test

`npm run test:e2e` expects a built frontend and a real API already running, and
a catalogue seeded by `backend/scripts/seed_catalog.py`. It does not start them,
because it tests the pair as they ship rather than a dev server nobody deploys.

Locally:

```bash
# with the database migrated and the API running
cd ../backend && python -m scripts.seed_catalog
cd ../frontend && npm run build && npx next start --port 3000 &
npx playwright install chromium
npm run test:e2e
```

Point it elsewhere with `E2E_BASE_URL`.

The seeded catalogue is four fixed postings rather than live data, so the
assertions are about behaviour and not about whatever the job board published
this morning.

## The container image

```bash
docker build --build-arg NEXT_PUBLIC_API_URL=https://api.example.com \
  -t skillsync-frontend .
docker run -p 3000:3000 -e SKILLSYNC_API_URL=http://api:8000 skillsync-frontend
```

The build refuses an empty `NEXT_PUBLIC_API_URL` rather than falling back to
the localhost default, because that fallback is inlined into the client bundle
and would fail in every visitor's browser instead of here.

`next.config.ts` sets `output: "standalone"`, so the runtime stage carries the
traced dependency set rather than a full install. That is what keeps the image
around 230 MB. Its entry point is `node server.js`, not `next start`, and it
binds `HOSTNAME` -- which the image sets to `0.0.0.0`, since the default binds
localhost and a container that does so publishes a port nothing answers on.

`frontend/scripts/smoke_test_image.sh` starts a built image and checks both:
that it answers from outside the container, and that the address it was built
with really reached the client bundle.

## No route-level loading file

`/jobs` deliberately has no `loading.tsx`. A route-level loading file makes the
route stream a fallback first, and swapping the real content in needs client
JavaScript, so the page showed "Loading jobs" forever without it. The browser
test runs one case with JavaScript disabled to keep that from coming back.

## Conventions

Components fetch through the typed client rather than calling `fetch` directly,
so request shapes stay in one place and stay tested.

No business logic, no direct database access. The frontend renders what the API
serves.
