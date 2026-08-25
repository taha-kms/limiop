export type WorkplacePreference = "remote" | "hybrid" | "onsite";
export type EmploymentPreference =
  "full-time" | "part-time" | "contract" | "internship" | "temporary";

export interface CandidateProfile {
  id: string;
  display_name: string | null;
  location: string | null;
  workplace_types: Array<WorkplacePreference | "unspecified"> | null;
  employment_types: Array<EmploymentPreference | "unspecified"> | null;
  headline: string | null;
  summary: string | null;
  years_experience: number | null;
  profile_complete: boolean;
  created_at: string;
  updated_at: string;
}

export interface SkillConceptSearchResult {
  concept_id: string;
  preferred_label: string;
}

export interface CandidateProfileSkill extends SkillConceptSearchResult {
  vocabulary_version: string;
  created_at: string;
}

export type CandidateProfileUpdate = Partial<
  Pick<
    CandidateProfile,
    | "display_name"
    | "location"
    | "workplace_types"
    | "employment_types"
    | "headline"
    | "summary"
    | "years_experience"
  >
>;

export class NotSignedInError extends Error {}
export class ProfileUnavailableError extends Error {}
export class ProfileRejectedError extends Error {}
export type SkillRefusalCode = "ambiguous_skill" | "unknown_skill";

export class SkillSelectionRejectedError extends Error {
  constructor(
    public readonly code: SkillRefusalCode,
    message: string,
  ) {
    super(message);
    this.name = "SkillSelectionRejectedError";
  }
}

async function request(path = "", init?: RequestInit): Promise<Response> {
  try {
    return await fetch(`/api/profile${path}`, {
      credentials: "same-origin",
      ...init,
      headers: { accept: "application/json", ...init?.headers },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ProfileUnavailableError("The profile service could not be reached.");
  }
}

async function read<ResponseBody>(response: Response): Promise<ResponseBody> {
  try {
    return (await response.json()) as ResponseBody;
  } catch {
    throw new ProfileUnavailableError("The profile service returned an unusable response.");
  }
}

function rejectProfile(response: Response): never {
  if (response.status === 401) {
    throw new NotSignedInError("Sign in to build your profile.");
  }
  if (response.status === 422) {
    throw new ProfileRejectedError("Check the highlighted profile fields.");
  }
  throw new ProfileUnavailableError("The profile service is unavailable.");
}

async function rejectSkill(response: Response): Promise<never> {
  if (response.status === 401) {
    throw new NotSignedInError("Sign in to manage your profile skills.");
  }
  if (response.status === 422) {
    const body = (await response.json().catch(() => null)) as {
      detail?: { code?: unknown; message?: unknown };
    } | null;
    const code = body?.detail?.code;
    const message = body?.detail?.message;
    if ((code === "ambiguous_skill" || code === "unknown_skill") && typeof message === "string") {
      throw new SkillSelectionRejectedError(code, message);
    }
    throw new ProfileRejectedError("That skill selection was not accepted.");
  }
  throw new ProfileUnavailableError("The profile skill service is unavailable.");
}

export async function getCandidateProfile(signal?: AbortSignal): Promise<CandidateProfile | null> {
  const response = await request("", { signal });
  if (response.ok) return read<CandidateProfile>(response);
  if (response.status === 404) return null;
  return rejectProfile(response);
}

export async function updateCandidateProfile(
  update: CandidateProfileUpdate,
): Promise<CandidateProfile> {
  const response = await request("", {
    method: "PATCH",
    body: JSON.stringify(update),
    headers: { "content-type": "application/json" },
  });
  if (response.ok) return read<CandidateProfile>(response);
  return rejectProfile(response);
}

export async function listCandidateProfileSkills(
  signal?: AbortSignal,
): Promise<CandidateProfileSkill[]> {
  const response = await request("/skills", { signal });
  if (response.ok) return read<CandidateProfileSkill[]>(response);
  return rejectSkill(response);
}

export async function searchSkillConcepts(
  query: string,
  signal?: AbortSignal,
): Promise<SkillConceptSearchResult[]> {
  const params = new URLSearchParams({ q: query.trim() });
  const response = await request(`/skills/search?${params.toString()}`, { signal });
  if (response.ok) return read<SkillConceptSearchResult[]>(response);
  return rejectSkill(response);
}

export async function addCandidateProfileSkill(conceptId: string): Promise<CandidateProfileSkill> {
  const response = await request("/skills", {
    method: "POST",
    body: JSON.stringify({ concept_id: conceptId }),
    headers: { "content-type": "application/json" },
  });
  if (response.ok) return read<CandidateProfileSkill>(response);
  return rejectSkill(response);
}

export async function removeCandidateProfileSkill(conceptId: string): Promise<void> {
  const response = await request(`/skills/${encodeURIComponent(conceptId)}`, {
    method: "DELETE",
  });
  if (response.ok) return;
  return rejectSkill(response);
}
