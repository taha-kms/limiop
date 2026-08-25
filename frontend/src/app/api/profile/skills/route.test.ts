import { cookies } from "next/headers";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GET, POST } from "./route";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

describe("profile skills proxy", () => {
  beforeEach(() => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "session=signed" } as never);
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("forwards profile skill reads with the session", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json([]));
    vi.stubGlobal("fetch", fetch);

    await GET();

    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/profile/skills",
      expect.objectContaining({
        method: "GET",
        headers: expect.objectContaining({ cookie: "session=signed" }),
      }),
    );
  });

  it("forwards only the selection body supplied by the client", async () => {
    const fetch = vi.fn().mockResolvedValue(Response.json({}, { status: 201 }));
    vi.stubGlobal("fetch", fetch);
    const body = JSON.stringify({ concept_id: "concept-id" });

    await POST(new Request("http://frontend/api/profile/skills", { method: "POST", body }));

    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/profile/skills",
      expect.objectContaining({
        method: "POST",
        body,
        headers: expect.objectContaining({ "content-type": "application/json" }),
      }),
    );
  });
});
