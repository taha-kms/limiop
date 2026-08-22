import { afterEach, describe, expect, it, vi } from "vitest";

import { apiUrl, browserApiUrl, serverApiUrl } from "./config";

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("browserApiUrl", () => {
  it("falls back to localhost when nothing is configured", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "");

    expect(browserApiUrl()).toBe("http://localhost:8000");
  });

  it("uses the configured address", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");

    expect(browserApiUrl()).toBe("https://api.example.com");
  });

  it("drops a trailing slash so paths join predictably", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com///");

    expect(browserApiUrl()).toBe("https://api.example.com");
  });

  it("refuses an address that is not a URL rather than building a broken one", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "api.example.com");

    expect(() => browserApiUrl()).toThrowError(/NEXT_PUBLIC_API_URL/);
  });
});

describe("serverApiUrl", () => {
  it("prefers its own address, because the server may reach the API elsewhere", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");

    expect(serverApiUrl()).toBe("http://api:8000");
  });

  it("falls back to the browser address when it has none", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    vi.stubEnv("SKILLSYNC_API_URL", "");

    expect(serverApiUrl()).toBe("https://api.example.com");
  });

  it("refuses an address that is not a URL", () => {
    vi.stubEnv("SKILLSYNC_API_URL", "not a url");

    expect(() => serverApiUrl()).toThrowError(/SKILLSYNC_API_URL/);
  });
});

describe("apiUrl", () => {
  it("uses the server address when there is no window", () => {
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
    const { window: original } = globalThis;
    Reflect.deleteProperty(globalThis, "window");

    try {
      expect(apiUrl()).toBe("http://api:8000");
    } finally {
      Object.defineProperty(globalThis, "window", { value: original, configurable: true });
    }
  });

  it("uses the browser address when a window exists", () => {
    vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");

    expect(apiUrl()).toBe("https://api.example.com");
  });
});
