/**
 * Where to return to after signing in.
 *
 * Only a path on this site is ever accepted. A `next` parameter is attacker
 * controlled — it arrives in a link anyone can send — so anything that could
 * name another origin is refused rather than sanitised. `//evil.example` and
 * `/\evil.example` are both browser-legal ways of writing an absolute URL, and
 * both are rejected here alongside anything carrying a scheme.
 */
const DEFAULT_DESTINATION = "/";

export function safeNextPath(value: string | string[] | undefined): string {
  if (typeof value !== "string") return DEFAULT_DESTINATION;
  if (!value.startsWith("/")) return DEFAULT_DESTINATION;
  if (value.startsWith("//") || value.startsWith("/\\")) return DEFAULT_DESTINATION;
  return value;
}
