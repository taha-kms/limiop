import { cookies } from "next/headers";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DELETE } from "./route";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

describe("profile skill removal proxy", () => {
  beforeEach(() => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "session=signed" } as never);
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("escapes and forwards the selected concept id", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);

    await DELETE(new Request("http://frontend"), {
      params: Promise.resolve({ conceptId: "../concept?bad=1" }),
    });

    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/profile/skills/..%2Fconcept%3Fbad%3D1",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
