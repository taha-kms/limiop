import { cookies } from "next/headers";

import { serverApiUrl } from "@/lib/config";

/** Statuses the fetch spec forbids a body on, empty or not. */
const EMPTY_BODY_STATUSES = new Set([204, 205, 304]);

/**
 * Talk to the account endpoints on the browser's behalf, both ways.
 *
 * The profile proxy only has to carry a cookie outward. These routes have to
 * carry one back: signing in and signing out are entirely a `Set-Cookie`, and
 * the session token is HttpOnly precisely so no script can hold it. Forwarding
 * the header verbatim keeps that true — the token passes through this route and
 * never through JavaScript.
 *
 * Same-origin, so the browser stores the cookie against the frontend rather
 * than against whatever address the API happens to be published on.
 */
export async function forwardAuth(
  path: string,
  method: "POST" | "DELETE",
  body?: string,
): Promise<Response> {
  const cookie = (await cookies()).toString();
  let upstream: Response;
  try {
    upstream = await fetch(`${serverApiUrl()}/api/v1${path}`, {
      method,
      body,
      cache: "no-store",
      headers: {
        accept: "application/json",
        ...(body ? { "content-type": "application/json" } : {}),
        ...(cookie ? { cookie } : {}),
      },
    });
  } catch {
    return Response.json({ detail: "the account service is unavailable" }, { status: 502 });
  }

  const headers = new Headers();
  // getSetCookie keeps several cookies separate; joining them would merge two
  // Set-Cookie headers into one the browser reads as a single malformed cookie.
  for (const value of upstream.headers.getSetCookie()) {
    headers.append("set-cookie", value);
  }

  // Carried back so the browser can say how long to wait rather than "later".
  const retryAfter = upstream.headers.get("retry-after");
  if (retryAfter) {
    headers.set("retry-after", retryAfter);
  }

  // Signing in and out answer 204, and the Response constructor refuses a body
  // with a status that forbids one — even an empty buffer. Passing the bytes
  // through unconditionally threw, which surfaced as a 500 on every sign-in.
  if (EMPTY_BODY_STATUSES.has(upstream.status)) {
    return new Response(null, { status: upstream.status, headers });
  }
  headers.set("content-type", upstream.headers.get("content-type") ?? "application/json");
  return new Response(await upstream.arrayBuffer(), { status: upstream.status, headers });
}
