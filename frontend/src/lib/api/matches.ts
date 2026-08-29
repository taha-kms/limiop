import { cookies } from "next/headers";

import { serverApiUrl } from "@/lib/config";
import type { JobSummary } from "@/lib/api/types";

/**
 * Ranked jobs for the signed-in candidate, read on the server.
 *
 * Read here rather than in the browser for the same reason the header is: the
 * session token is HttpOnly, so a server component can use it and a script
 * cannot, and the page arrives complete instead of empty and filling in.
 */
export interface MatchedSkill {
  concept_id: string;
  preferred_label: string;
}

export interface JobMatch {
  job: JobSummary;
  score: number;
  matched_skills: MatchedSkill[];
  missing_skills: MatchedSkill[];
}

export interface MatchList {
  matches: JobMatch[];
  ranked: number;
}

/** The API refused the session. The caller sends the visitor to sign in. */
export class NotSignedInError extends Error {
  constructor() {
    super("You are not signed in.");
    this.name = "NotSignedInError";
  }
}

/** Anything else. The page says so rather than rendering an empty ranking. */
export class MatchesUnavailableError extends Error {
  constructor() {
    super("Your matches could not be read.");
    this.name = "MatchesUnavailableError";
  }
}

export async function getMatches(limit = 20): Promise<MatchList> {
  const cookie = (await cookies()).toString();
  if (!cookie) throw new NotSignedInError();

  let response: Response;
  try {
    response = await fetch(`${serverApiUrl()}/api/v1/matches?limit=${limit}`, {
      cache: "no-store",
      headers: { accept: "application/json", cookie },
    });
  } catch {
    throw new MatchesUnavailableError();
  }

  if (response.status === 401) throw new NotSignedInError();
  if (!response.ok) throw new MatchesUnavailableError();
  return (await response.json()) as MatchList;
}
