import { forwardProfile } from "./_proxy";

export async function GET(): Promise<Response> {
  return forwardProfile("", "GET");
}

export async function PATCH(request: Request): Promise<Response> {
  return forwardProfile("", "PATCH", await request.text());
}
