import { forwardAuth } from "../_proxy";

/**
 * Delete the signed-in account.
 *
 * Through the auth proxy because the response is a `Set-Cookie`: the API
 * clears the session on the way out, and that header has to reach the browser
 * for the account to stop looking signed in.
 */
export async function DELETE(request: Request): Promise<Response> {
  return forwardAuth("/me", "DELETE", await request.text());
}
