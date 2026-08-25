import { afterEach, describe, expect, it, vi } from "vitest";

import {
  addCandidateProfileSkill,
  getCandidateProfile,
  listCandidateProfileSkills,
  NotSignedInError,
  ProfileRejectedError,
  ProfileUnavailableError,
  removeCandidateProfileSkill,
  searchSkillConcepts,
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

  it("searches canonical concepts and sends only an id when selecting one", async () => {
    const concept = { concept_id: "postgres-id", preferred_label: "PostgreSQL" };
    const stored = {
      ...concept,
      vocabulary_version: "test.1",
      created_at: "2026-08-25T00:00:00Z",
    };
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response([concept]))
      .mockResolvedValueOnce(response(stored, 201));
    vi.stubGlobal("fetch", fetch);

    await expect(searchSkillConcepts("  Postgre  ")).resolves.toEqual([concept]);
    await expect(addCandidateProfileSkill(concept.concept_id)).resolves.toEqual(stored);

    expect(fetch).toHaveBeenNthCalledWith(
      1,
      "/api/profile/skills/search?q=Postgre",
      expect.objectContaining({ credentials: "same-origin" }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/profile/skills",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ concept_id: "postgres-id" }),
      }),
    );
  });

  it("lists and removes stored profile skills", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);

    await expect(listCandidateProfileSkills()).resolves.toEqual([]);
    await expect(removeCandidateProfileSkill("concept/id")).resolves.toBeUndefined();

    expect(fetch).toHaveBeenLastCalledWith(
      "/api/profile/skills/concept%2Fid",
      expect.objectContaining({ method: "DELETE" }),
    );
  });

  it.each([
    ["ambiguous_skill", "ambiguous"],
    ["unknown_skill", "not in the canonical vocabulary"],
  ] as const)("preserves the %s refusal", async (code, message) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({ detail: { code, message } }, 422)));

    await expect(addCandidateProfileSkill("concept-id")).rejects.toMatchObject({
      name: "SkillSelectionRejectedError",
      code,
      message,
    });
  });
});
