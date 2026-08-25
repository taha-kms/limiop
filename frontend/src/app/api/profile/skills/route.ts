import { forwardProfile } from "../_proxy";

export async function GET(): Promise<Response> {
  return forwardProfile("/skills", "GET");
}

export async function POST(request: Request): Promise<Response> {
  return forwardProfile("/skills", "POST", await request.text());
}
