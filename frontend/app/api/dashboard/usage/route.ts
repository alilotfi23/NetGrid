import { NextResponse } from "next/server";

import { loadUsage } from "@/lib/api";

/**
 * BFF proxy for the data-cap usage dashboard card. The client polls this
 * endpoint (instead of the backend) so the session token in the HttpOnly
 * cookie stays server-side. Returns the same result envelope the server
 * component renders with.
 */
export async function GET() {
  const result = await loadUsage();
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return NextResponse.json(result);
}
