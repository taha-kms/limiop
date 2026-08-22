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
```

CI runs all five. `npm run typecheck` regenerates the route types first,
because Next derives `PageProps` and `LayoutProps` from the files on disk and
stale types would hide a broken route.

## Conventions

Components fetch through the typed client rather than calling `fetch` directly,
so request shapes stay in one place and stay tested.

No business logic, no direct database access. The frontend renders what the API
serves.
