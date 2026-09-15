FROM node:26.8.1-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS builder

WORKDIR /build

# The lockfile first, so a source-only change reuses the install layer.
COPY package.json package-lock.json ./
RUN npm clean-install

COPY . .

# Inlined into the client bundle rather than read at runtime, which is what
# makes this image specific to the address it will be served from. Unset, the
# fallback in src/lib/config.ts would bake `http://localhost:8000` into every
# visitor's browser and fail there rather than here, so the build refuses it.
ARG NEXT_PUBLIC_API_URL
RUN test -n "${NEXT_PUBLIC_API_URL}" \
    || { echo "NEXT_PUBLIC_API_URL must be set: it is inlined into the client bundle" >&2; exit 1; }
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

RUN npm run build

FROM node:26.8.1-alpine@sha256:2d984a15c9b54fd0aeb608b8e0d0d83529eb34d2966db27a1fb4f1edc3d298a3 AS runtime

ENV NODE_ENV=production \
    PORT=3000 \
    # The standalone server binds HOSTNAME, and its default is localhost. Left
    # there, the published port maps to a server listening only inside the
    # container and nothing outside it ever gets an answer.
    HOSTNAME=0.0.0.0

WORKDIR /app

# The traced server and its dependencies, then the client assets, which the
# trace does not cover because nothing on the server imports them.
COPY --from=builder --chown=node:node /build/.next/standalone ./
COPY --from=builder --chown=node:node /build/.next/static ./.next/static

USER node

EXPOSE 3000

CMD ["node", "server.js"]
