import { forwardAuth } from "../../_proxy";

/**
 * End every session, this device included.
 *
 * The sibling route clears one cookie. This one invalidates the tokens, so a
 * device that still holds an unexpired one is refused rather than merely asked
 * to sign in again.
 */
export async function DELETE(): Promise<Response> {
  return forwardAuth("/sessions/all", "DELETE");
}
