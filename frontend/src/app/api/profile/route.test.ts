import { cookies } from "next/headers";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, PATCH } from "./route";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

function upstream(body: object, status = 200): Response {
  return Response.json(body, { status });
}

describe("profile proxy", () => {
  beforeEach(() => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "session=signed" } as never);
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("forwards the HttpOnly session on reads", async () => {
    const fetch = vi.fn().mockResolvedValue(upstream({ profile_complete: false }));
    vi.stubGlobal("fetch", fetch);

    const response = await GET();

    expect(response.status).toBe(200);
    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/profile",
      expect.objectContaining({
        method: "GET",
        cache: "no-store",
        headers: expect.objectContaining({ cookie: "session=signed" }),
      }),
    );
  });

  it("forwards one partial profile write and its response", async () => {
    const fetch = vi.fn().mockResolvedValue(upstream({ display_name: "Ada" }));
    vi.stubGlobal("fetch", fetch);

    const response = await PATCH(
      new Request("http://frontend/api/profile", {
        method: "PATCH",
        body: JSON.stringify({ display_name: "Ada" }),
      }),
    );

    expect(await response.json()).toEqual({ display_name: "Ada" });
    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/profile",
      expect.objectContaining({
        method: "PATCH",
        body: JSON.stringify({ display_name: "Ada" }),
        headers: expect.objectContaining({ "content-type": "application/json" }),
      }),
    );
  });

  it("turns an unreachable backend into a safe gateway response", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const response = await GET();

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ detail: "profile service unavailable" });
  });
});
