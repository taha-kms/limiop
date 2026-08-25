import { forwardProfile } from "../../_proxy";

interface RouteContext {
  params: Promise<{ conceptId: string }>;
}

export async function DELETE(_request: Request, context: RouteContext): Promise<Response> {
  const { conceptId } = await context.params;
  return forwardProfile(`/skills/${encodeURIComponent(conceptId)}`, "DELETE");
}
