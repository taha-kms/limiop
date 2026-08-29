import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getMarketInsights, InsightsUnavailableError } from "./analytics";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

function answer(path: string): Response {
  if (path.includes("/skills")) return Response.json({ skills: [] });
  if (path.includes("/locations")) return Response.json({ locations: [], workplace_types: [] });
  return Response.json({ bucket: "month", points: [] });
}

describe("getMarketInsights", () => {
  it("reads all three aggregates and never caches an hourly catalogue", async () => {
    fetchMock.mockImplementation((url: string) => Promise.resolve(answer(url)));

    const insights = await getMarketInsights();

    expect(insights.bucket).toBe("month");
    expect(fetchMock).toHaveBeenCalledTimes(3);
    for (const [, init] of fetchMock.mock.calls) expect(init.cache).toBe("no-store");
  });

  it("sends no cookie, because the aggregates are public", async () => {
    fetchMock.mockImplementation((url: string) => Promise.resolve(answer(url)));

    await getMarketInsights();

    for (const [, init] of fetchMock.mock.calls) {
      expect(init.headers).not.toHaveProperty("cookie");
    }
  });

  it.each([
    ["a failing API", () => fetchMock.mockResolvedValue(new Response(null, { status: 500 }))],
    ["an unreachable API", () => fetchMock.mockRejectedValue(new TypeError("network"))],
  ])("reports %s rather than an empty market", async (_name, arrange) => {
    arrange();

    await expect(getMarketInsights()).rejects.toBeInstanceOf(InsightsUnavailableError);
  });

  it("asks every aggregate the same narrowing question", async () => {
    fetchMock.mockImplementation((url: string) => Promise.resolve(answer(url)));

    await getMarketInsights({ since: "2026-01-01T00:00:00.000Z", sourceKey: "greenhouse" });

    for (const [url] of fetchMock.mock.calls) {
      expect(url).toContain("since=2026-01-01T00%3A00%3A00.000Z");
      expect(url).toContain("source_key=greenhouse");
    }
  });

  it("omits a narrowing nobody asked for rather than sending an empty one", async () => {
    fetchMock.mockImplementation((url: string) => Promise.resolve(answer(url)));

    await getMarketInsights();

    for (const [url] of fetchMock.mock.calls) {
      expect(url).not.toContain("since=");
      expect(url).not.toContain("source_key=");
    }
  });
});
