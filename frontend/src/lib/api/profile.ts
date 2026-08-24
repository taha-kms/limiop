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

async function request(init?: RequestInit): Promise<Response> {
  try {
    return await fetch("/api/profile", {
      credentials: "same-origin",
      ...init,
      headers: { accept: "application/json", ...init?.headers },
    });
  } catch (cause) {
    if (cause instanceof DOMException && cause.name === "AbortError") throw cause;
    throw new ProfileUnavailableError("The profile service could not be reached.");
  }
}

async function read(response: Response): Promise<CandidateProfile> {
  try {
    return (await response.json()) as CandidateProfile;
  } catch {
    throw new ProfileUnavailableError("The profile service returned an unusable response.");
  }
}

function reject(response: Response): never {
  if (response.status === 401) {
    throw new NotSignedInError("Sign in to build your profile.");
  }
  if (response.status === 422) {
    throw new ProfileRejectedError("Check the highlighted profile fields.");
  }
  throw new ProfileUnavailableError("The profile service is unavailable.");
}

export async function getCandidateProfile(signal?: AbortSignal): Promise<CandidateProfile | null> {
  const response = await request({ signal });
  if (response.ok) return read(response);
  if (response.status === 404) return null;
  return reject(response);
}

export async function updateCandidateProfile(
  update: CandidateProfileUpdate,
): Promise<CandidateProfile> {
  const response = await request({
    method: "PATCH",
    body: JSON.stringify(update),
    headers: { "content-type": "application/json" },
  });
  if (response.ok) return read(response);
  return reject(response);
}
