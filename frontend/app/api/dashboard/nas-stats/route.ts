import { NextResponse } from "next/server";

import { loadNasDevices } from "@/lib/api";

/**
 * BFF proxy for the NAS dashboard cards (summary + by-type breakdown, which
 * share the same stats). The client polls this endpoint (instead of the
 * backend) so the session token in the HttpOnly cookie stays server-side.
 * Returns the same result envelope the server components render with.
 */
export async function GET() {
  const result = await loadNasDevices();
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return NextResponse.json(result);
}
