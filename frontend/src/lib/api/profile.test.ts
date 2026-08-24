import { afterEach, describe, expect, it, vi } from "vitest";

import {
  getCandidateProfile,
  NotSignedInError,
  ProfileRejectedError,
  ProfileUnavailableError,
  updateCandidateProfile,
} from "./profile";

function response(body: object, status = 200): Response {
  return Response.json(body, { status });
}

afterEach(() => vi.unstubAllGlobals());

describe("candidate profile client", () => {
  it("returns no profile for a candidate who has not started", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: "missing" }, 404)));

    await expect(getCandidateProfile()).resolves.toBeNull();
  });

  it("sends partial updates through the same-origin session boundary", async () => {
    const profile = { id: "profile", display_name: "Ada", profile_complete: false };
    const fetch = vi.fn().mockResolvedValue(response(profile));
    vi.stubGlobal("fetch", fetch);

    await expect(updateCandidateProfile({ display_name: "Ada" })).resolves.toEqual(profile);
    expect(fetch).toHaveBeenCalledWith(
      "/api/profile",
      expect.objectContaining({
        credentials: "same-origin",
        method: "PATCH",
        body: JSON.stringify({ display_name: "Ada" }),
      }),
    );
  });

  it("names authentication, validation, and availability failures", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({}, 401))
      .mockResolvedValueOnce(response({}, 422))
      .mockResolvedValueOnce(response({}, 502));
    vi.stubGlobal("fetch", fetch);

    await expect(getCandidateProfile()).rejects.toBeInstanceOf(NotSignedInError);
    await expect(updateCandidateProfile({ location: "London" })).rejects.toBeInstanceOf(
      ProfileRejectedError,
    );
    await expect(getCandidateProfile()).rejects.toBeInstanceOf(ProfileUnavailableError);
  });
});
