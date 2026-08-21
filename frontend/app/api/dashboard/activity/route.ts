import { NextResponse } from "next/server";

import { loadAuditLogs } from "@/lib/api";

const ENTRY_COUNT = 8;

/**
 * BFF proxy for the dashboard recent-activity feed. The client polls this
 * endpoint (instead of the backend) so the session token in the HttpOnly
 * cookie stays server-side. Returns the same result envelope the server
 * component renders with, so the polling client can reuse it verbatim.
 */
export async function GET() {
  const result = await loadAuditLogs({ pageSize: ENTRY_COUNT });
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return NextResponse.json(result);
}
