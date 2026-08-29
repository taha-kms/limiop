import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cookies = vi.hoisted(() => vi.fn());
vi.mock("next/headers", () => ({ cookies }));

import { getMatches, MatchesUnavailableError, NotSignedInError } from "./matches";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  cookies.mockReset().mockResolvedValue({ toString: () => "session=signed" });
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("getMatches", () => {
  it("forwards the session and never caches a personal ranking", async () => {
    fetchMock.mockResolvedValue(Response.json({ matches: [], ranked: 0 }));

    await expect(getMatches()).resolves.toEqual({ matches: [], ranked: 0 });

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("http://api:8000/api/v1/matches?limit=20");
    expect(init.cache).toBe("no-store");
    expect(init.headers.cookie).toBe("session=signed");
  });

  it("asks nothing when there is no cookie to ask with", async () => {
    cookies.mockResolvedValue({ toString: () => "" });

    await expect(getMatches()).rejects.toBeInstanceOf(NotSignedInError);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("reports a refused session as such, so the page can send them to sign in", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 401 }));

    await expect(getMatches()).rejects.toBeInstanceOf(NotSignedInError);
  });

  it.each([
    ["a failing API", () => fetchMock.mockResolvedValue(new Response(null, { status: 500 }))],
    ["an unreachable API", () => fetchMock.mockRejectedValue(new TypeError("network"))],
  ])("reports %s as unavailable rather than as no matches", async (_name, arrange) => {
    arrange();

    await expect(getMatches()).rejects.toBeInstanceOf(MatchesUnavailableError);
  });
});
