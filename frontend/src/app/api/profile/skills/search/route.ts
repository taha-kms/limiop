import { forwardProfile } from "../../_proxy";

export async function GET(request: Request): Promise<Response> {
  const query = new URL(request.url).searchParams.toString();
  return forwardProfile(`/skills/search?${query}`, "GET");
}
