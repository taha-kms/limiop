import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  AuthUnavailableError,
  CredentialsRejectedError,
  RegistrationRefusedError,
  register,
  signIn,
  signOut,
} from "./auth";

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});
afterEach(() => vi.unstubAllGlobals());

function answered(status: number): Response {
  return new Response(null, { status });
}

describe("signIn", () => {
  it("succeeds on the API's 204, which carries the session only as a cookie", async () => {
    fetchMock.mockResolvedValue(answered(204));

    await expect(signIn({ email: "a@b.example", password: "x" })).resolves.toBeUndefined();

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe("/api/auth/session");
    expect(init.credentials).toBe("same-origin");
  });

  it("reports a rejection without saying which half was wrong", async () => {
    fetchMock.mockResolvedValue(answered(401));

    await expect(signIn({ email: "a@b.example", password: "x" })).rejects.toBeInstanceOf(
      CredentialsRejectedError,
    );
  });

  it("does not distinguish a malformed request from a wrong password", async () => {
    // A 422 means this client sent something the API would not parse. Telling a
    // visitor that the address was not an address would confirm the other half.
    fetchMock.mockResolvedValue(answered(422));

    await expect(signIn({ email: "nope", password: "x" })).rejects.toBeInstanceOf(
      CredentialsRejectedError,
    );
  });

  it("reports anything else as the service failing, not the credentials", async () => {
    fetchMock.mockResolvedValue(answered(500));

    await expect(signIn({ email: "a@b.example", password: "x" })).rejects.toBeInstanceOf(
      AuthUnavailableError,
    );
  });

  it("treats an unreachable service as its own failure", async () => {
    fetchMock.mockRejectedValue(new TypeError("network"));

    await expect(signIn({ email: "a@b.example", password: "x" })).rejects.toBeInstanceOf(
      AuthUnavailableError,
    );
  });
});

describe("register", () => {
  it("succeeds on 201", async () => {
    fetchMock.mockResolvedValue(answered(201));

    await expect(
      register({ email: "a@b.example", password: "x".repeat(12) }),
    ).resolves.toBeUndefined();
  });

  it("repeats the API's refusal to say why, so addresses cannot be enumerated", async () => {
    fetchMock.mockResolvedValue(answered(409));

    await expect(register({ email: "taken@b.example", password: "x".repeat(12) })).rejects.toThrow(
      "That account could not be created.",
    );
  });

  it("reports an unreachable service rather than blaming the address", async () => {
    fetchMock.mockResolvedValue(answered(500));

    await expect(
      register({ email: "a@b.example", password: "x".repeat(12) }),
    ).rejects.toBeInstanceOf(AuthUnavailableError);
  });

  it("explains a rejected password without echoing it", async () => {
    fetchMock.mockResolvedValue(answered(422));

    const failure = await register({ email: "a@b.example", password: "short" }).catch(
      (cause: unknown) => cause,
    );

    expect(failure).toBeInstanceOf(RegistrationRefusedError);
    expect((failure as Error).message).not.toContain("short");
  });
});

describe("signOut", () => {
  it("sends a DELETE for this device", async () => {
    fetchMock.mockResolvedValue(answered(204));

    await signOut();

    expect(fetchMock.mock.calls[0][1].method).toBe("DELETE");
    expect(fetchMock.mock.calls[0][0]).toBe("/api/auth/session");
  });

  it("reports an unreachable service on sign-out too", async () => {
    fetchMock.mockRejectedValue(new TypeError("network"));

    await expect(signOut()).rejects.toBeInstanceOf(AuthUnavailableError);
  });

  it("fails loudly rather than pretending the session ended", async () => {
    fetchMock.mockResolvedValue(answered(500));

    await expect(signOut()).rejects.toBeInstanceOf(AuthUnavailableError);
  });
});
