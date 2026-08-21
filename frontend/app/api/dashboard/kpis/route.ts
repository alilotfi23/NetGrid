import { NextResponse } from "next/server";

import { loadDashboardKpis } from "@/lib/api";

/**
 * BFF proxy for the dashboard KPI strip. The client polls this endpoint
 * (instead of the backend) so the session token in the HttpOnly cookie
 * stays server-side. Returns the same result envelope the server component
 * renders with, so the polling client can reuse it verbatim.
 */
export async function GET() {
  const result = await loadDashboardKpis();
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return NextResponse.json(result);
}
