import { cookies } from "next/headers";

import { serverApiUrl } from "@/lib/config";

type ProfileMethod = "GET" | "PATCH" | "POST" | "DELETE";

export async function forwardProfile(
  path: string,
  method: ProfileMethod,
  body?: string,
): Promise<Response> {
  const cookie = (await cookies()).toString();
  try {
    const response = await fetch(`${serverApiUrl()}/api/v1/profile${path}`, {
      method,
      body,
      cache: "no-store",
      headers: {
        accept: "application/json",
        ...(body ? { "content-type": "application/json" } : {}),
        ...(cookie ? { cookie } : {}),
      },
    });
    return new Response(await response.arrayBuffer(), {
      status: response.status,
      headers: { "content-type": response.headers.get("content-type") ?? "application/json" },
    });
  } catch {
    return Response.json({ detail: "profile service unavailable" }, { status: 502 });
  }
}
