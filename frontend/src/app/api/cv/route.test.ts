import { cookies } from "next/headers";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE } from "./route";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

function request(query: string): Request {
  return new Request(`http://frontend/api/cv${query}`, { method: "DELETE" });
}

describe("the CV delete proxy", () => {
  beforeEach(() => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "session=signed" } as never);
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("forwards the session and the identifier", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);

    const response = await DELETE(request("?id=abc"));

    expect(response.status).toBe(204);
    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/cvs/abc",
      expect.objectContaining({
        method: "DELETE",
        headers: expect.objectContaining({ cookie: "session=signed" }),
      }),
    );
  });

  it("refuses a request that names no CV rather than guessing one", async () => {
    const fetch = vi.fn();
    vi.stubGlobal("fetch", fetch);

    expect((await DELETE(request(""))).status).toBe(400);
    expect((await DELETE(request("?id=%20"))).status).toBe(400);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("says so when the API cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("network")));

    expect((await DELETE(request("?id=abc"))).status).toBe(502);
  });
});
