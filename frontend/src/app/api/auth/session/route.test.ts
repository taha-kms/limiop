import { cookies } from "next/headers";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { POST as REGISTER } from "../register/route";
import { DELETE, POST } from "./route";

vi.mock("next/headers", () => ({ cookies: vi.fn() }));

const SESSION = "session=token; HttpOnly; Path=/; SameSite=lax";

function signedInUpstream(status: number, cookies: string[] = [SESSION]): Response {
  const headers = new Headers();
  for (const value of cookies) headers.append("set-cookie", value);
  return new Response(null, { status, headers });
}

function signIn(body: object): Request {
  return new Request("http://frontend/api/auth/session", {
    method: "POST",
    body: JSON.stringify(body),
  });
}

describe("account proxy", () => {
  beforeEach(() => {
    vi.mocked(cookies).mockResolvedValue({ toString: () => "" } as never);
    vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
  });

  it("carries the session cookie back to the browser", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(signedInUpstream(204)));

    const response = await POST(signIn({ email: "a@b.example", password: "x" }));

    expect(response.status).toBe(204);
    expect(response.headers.getSetCookie()).toEqual([SESSION]);
  });

  it("returns a 204 with no body at all", async () => {
    // The Response constructor refuses a body on a status that forbids one,
    // even an empty buffer. Passing the bytes through unconditionally threw,
    // and it surfaced as a 500 on every sign-in and nothing else.
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(signedInUpstream(204)));

    const response = await POST(signIn({ email: "a@b.example", password: "x" }));

    expect(response.body).toBeNull();
    expect(response.headers.get("content-type")).toBeNull();
  });

  it("keeps several cookies separate rather than joining them", async () => {
    const extra = "other=value; Path=/";
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(signedInUpstream(204, [SESSION, extra])));

    const response = await POST(signIn({ email: "a@b.example", password: "x" }));

    expect(response.headers.getSetCookie()).toEqual([SESSION, extra]);
  });

  it("passes a refusal through with its body", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ detail: "those credentials were not accepted" }, { status: 401 }),
        ),
    );

    const response = await POST(signIn({ email: "a@b.example", password: "wrong" }));

    expect(response.status).toBe(401);
    expect(await response.json()).toEqual({ detail: "those credentials were not accepted" });
  });

  it("signs out this device, and forwards the cookie that clears it", async () => {
    const cleared = "session=; Max-Age=0; Path=/";
    const fetch = vi.fn().mockResolvedValue(signedInUpstream(204, [cleared]));
    vi.mocked(cookies).mockResolvedValue({ toString: () => "session=token" } as never);
    vi.stubGlobal("fetch", fetch);

    const response = await DELETE();

    expect(response.headers.getSetCookie()).toEqual([cleared]);
    expect(fetch).toHaveBeenCalledWith(
      "http://api:8000/api/v1/sessions",
      expect.objectContaining({
        method: "DELETE",
        headers: expect.objectContaining({ cookie: "session=token" }),
      }),
    );
  });

  it("registers against the accounts endpoint, not the sessions one", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValue(Response.json({ id: "u1", email: "a@b.example" }, { status: 201 }));
    vi.stubGlobal("fetch", fetch);

    const response = await REGISTER(signIn({ email: "a@b.example", password: "x".repeat(12) }));

    expect(response.status).toBe(201);
    expect(fetch.mock.calls[0][0]).toBe("http://api:8000/api/v1/accounts");
  });

  it("turns an unreachable API into a gateway response rather than a crash", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("offline")));

    const response = await POST(signIn({ email: "a@b.example", password: "x" }));

    expect(response.status).toBe(502);
    expect(await response.json()).toEqual({ detail: "the account service is unavailable" });
  });
});
