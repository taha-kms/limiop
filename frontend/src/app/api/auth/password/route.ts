import { forwardAuth } from "../_proxy";

/**
 * Replace the signed-in account's password.
 *
 * Through the auth proxy because the response is a `Set-Cookie`: changing a
 * password ends every session, and the API re-issues one for this device under
 * the new token version. Without that header reaching the browser, the change
 * would sign the caller out of the page they made it on.
 */
export async function POST(request: Request): Promise<Response> {
  return forwardAuth("/me/password", "POST", await request.text());
}
