import { NextResponse } from "next/server";

import { loadSessions } from "@/lib/api";

/**
 * BFF proxy for the live-sessions card. The client polls this endpoint
 * (instead of the backend) so the session token in the HttpOnly cookie
 * stays server-side. Returns the same result envelope the server component
 * renders with.
 */
export async function GET() {
  const result = await loadSessions();
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return NextResponse.json(result);
}
