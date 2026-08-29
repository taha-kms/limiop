import { forwardAuth } from "../_proxy";

export async function POST(request: Request): Promise<Response> {
  return forwardAuth("/sessions", "POST", await request.text());
}

/** This device only. Ending every session is a different endpoint. */
export async function DELETE(): Promise<Response> {
  return forwardAuth("/sessions", "DELETE");
}
