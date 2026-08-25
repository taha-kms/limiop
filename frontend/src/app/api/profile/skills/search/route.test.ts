import { cookies } from "next/headers";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET } from "./route";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

describe("profile skill search proxy", () => {
  beforeEach(() => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "session=signed" } as never);
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("forwards the encoded query and session", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json([]));
    vi.stubGlobal("fetch", fetch);

    await GET(new Request("http://frontend/api/profile/skills/search?q=C%2B%2B"));

    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/profile/skills/search?q=C%2B%2B",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ cookie: "session=signed" }),
      }),
    );
  });
});
