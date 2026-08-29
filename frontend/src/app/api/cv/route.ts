import { cookies } from "next/headers";

import { serverApiUrl } from "@/lib/config";

/**
 * The CV endpoints, proxied same-origin so the session cookie applies.
 *
 * The upload body is streamed through rather than parsed here: it is a PDF up
 * to several megabytes, and re-encoding it in this hop would double the memory
 * for no gain. The API is what enforces the policy, so nothing is validated
 * twice either.
 */
async function forward(method: "GET" | "POST", request?: Request): Promise<Response> {
  const cookie = (await cookies()).toString();
  let upstream: Response;
  try {
    upstream = await fetch(`${serverApiUrl()}/api/v1/cvs`, {
      method,
      cache: "no-store",
      headers: {
        accept: "application/json",
        ...(cookie ? { cookie } : {}),
        ...(request?.headers.get("content-type")
          ? { "content-type": request.headers.get("content-type") as string }
          : {}),
      },
      body: request ? await request.arrayBuffer() : undefined,
    });
  } catch {
    return Response.json({ detail: "the CV service is unavailable" }, { status: 502 });
  }

  return new Response(await upstream.arrayBuffer(), {
    status: upstream.status,
    headers: { "content-type": upstream.headers.get("content-type") ?? "application/json" },
  });
}

export async function GET(): Promise<Response> {
  return forward("GET");
}

export async function POST(request: Request): Promise<Response> {
  return forward("POST", request);
}
