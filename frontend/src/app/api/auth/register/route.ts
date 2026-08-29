import { forwardAuth } from "../_proxy";

export async function POST(request: Request): Promise<Response> {
  return forwardAuth("/accounts", "POST", await request.text());
}
