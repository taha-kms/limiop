import { cookies } from "next/headers";

import { serverApiUrl } from "@/lib/config";

/**
 * Who is signed in, read on the server.
 *
 * The session token is in an HttpOnly cookie, which a server component can read
 * and a script cannot. Reading it here rather than in the browser is what keeps
 * a personalized page rendering complete on first byte instead of arriving
 * empty and filling in.
 *
 * Returns null for every reason a request can fail to identify someone — no
 * cookie, an expired token, a revoked session, an unreachable API. The caller
 * has the same recourse in all of them, so they are not distinguished.
 */
export interface SignedInAccount {
  id: string;
  email: string;
}

export async function currentAccount(): Promise<SignedInAccount | null> {
  const cookie = (await cookies()).toString();
  if (!cookie) return null;
  try {
    const response = await fetch(`${serverApiUrl()}/api/v1/me`, {
      cache: "no-store",
      headers: { accept: "application/json", cookie },
    });
    if (!response.ok) return null;
    const account: unknown = await response.json();
    if (
      typeof account !== "object" ||
      account === null ||
      typeof (account as SignedInAccount).email !== "string"
    ) {
      return null;
    }
    return account as SignedInAccount;
  } catch {
    return null;
  }
}
