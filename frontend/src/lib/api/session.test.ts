import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const cookies = vi.hoisted(() => vi.fn());
vi.mock("next/headers", () => ({ cookies }));

import { currentAccount } from "./session";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  cookies.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function withCookie(value: string) {
  cookies.mockResolvedValue({ toString: () => value });
}

describe("currentAccount", () => {
  it("returns the account the API names", async () => {
    withCookie("session=abc");
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ id: "u1", email: "a@b.example" }), { status: 200 }),
    );

    await expect(currentAccount()).resolves.toEqual({ id: "u1", email: "a@b.example" });

    const [, init] = fetchMock.mock.calls[0];
    expect(init.headers.cookie).toBe("session=abc");
    // A stale account read is worse than none: the header would name whoever
    // was signed in when the page was last cached.
    expect(init.cache).toBe("no-store");
  });

  it("asks nothing when there is no cookie to ask with", async () => {
    withCookie("");

    await expect(currentAccount()).resolves.toBeNull();
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it.each([
    ["a refused session", () => fetchMock.mockResolvedValue(new Response(null, { status: 401 }))],
    ["an unreachable API", () => fetchMock.mockRejectedValue(new TypeError("network"))],
    [
      "a response that is not an account",
      () => fetchMock.mockResolvedValue(new Response("[]", { status: 200 })),
    ],
  ])("reports nobody for %s", async (_name, arrange) => {
    withCookie("session=abc");
    arrange();

    await expect(currentAccount()).resolves.toBeNull();
  });
});
