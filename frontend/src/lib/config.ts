/**
 * Where the frontend finds the API.
 *
 * Two variables rather than one, because the browser and the server do not
 * reach the API at the same address. In a container the server talks to it over
 * the compose network while the browser talks to a published port, and a single
 * value cannot be right for both.
 *
 * Neither is a secret. The catalogue API is public and unauthenticated, so
 * these are configuration, not credentials.
 */

const DEFAULT_API_URL = "http://localhost:8000";

function readApiUrl(value: string | undefined, name: string): string {
  const raw = value?.trim() ? value.trim() : DEFAULT_API_URL;
  try {
    new URL(raw);
  } catch {
    throw new Error(`${name} must be an absolute URL, received ${JSON.stringify(raw)}`);
  }
  return raw.replace(/\/+$/, "");
}

/** The address the browser uses. Inlined at build time, so it must be public. */
export function browserApiUrl(): string {
  return readApiUrl(process.env.NEXT_PUBLIC_API_URL, "NEXT_PUBLIC_API_URL");
}

/** The address the server uses, falling back to the browser's when unset. */
export function serverApiUrl(): string {
  const configured = process.env.SKILLSYNC_API_URL;
  return configured?.trim() ? readApiUrl(configured, "SKILLSYNC_API_URL") : browserApiUrl();
}

/** The address for wherever this code happens to be running. */
export function apiUrl(): string {
  return typeof window === "undefined" ? serverApiUrl() : browserApiUrl();
}
