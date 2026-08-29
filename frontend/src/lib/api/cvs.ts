import { cookies } from "next/headers";

import { serverApiUrl } from "@/lib/config";

/** How a stored CV is progressing. Mirrors the API's own vocabulary. */
export type CVProcessingState = "pending" | "processing" | "processed" | "failed";

export interface StoredCV {
  id: string;
  media_type: string;
  size_bytes: number;
  processing_state: CVProcessingState;
  created_at: string;
}

export class NotSignedInError extends Error {
  constructor() {
    super("You are not signed in.");
    this.name = "NotSignedInError";
  }
}

export class CVUnavailableError extends Error {
  constructor() {
    super("Your CV could not be read.");
    this.name = "CVUnavailableError";
  }
}

/** The owner's most recent CV, read on the server, or null when there is none. */
export async function getStoredCV(): Promise<StoredCV | null> {
  const cookie = (await cookies()).toString();
  if (!cookie) throw new NotSignedInError();

  let response: Response;
  try {
    response = await fetch(`${serverApiUrl()}/api/v1/cvs`, {
      cache: "no-store",
      headers: { accept: "application/json", cookie },
    });
  } catch {
    throw new CVUnavailableError();
  }

  if (response.status === 401) throw new NotSignedInError();
  if (!response.ok) throw new CVUnavailableError();
  return (await response.json()) as StoredCV | null;
}
