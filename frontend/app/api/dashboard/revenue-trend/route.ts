import { NextResponse } from "next/server";

import { loadPaymentsReport } from "@/lib/api";
import { buildRevenueTrend } from "@/lib/revenue-trend";

/**
 * BFF proxy for the revenue-trend dashboard card. The client polls this
 * endpoint (instead of the backend) so the session token in the HttpOnly
 * cookie stays server-side. The trailing-12-month series is built here,
 * server-side, so the client only ever sees ready-to-render points.
 */
export async function GET() {
  const result = await loadPaymentsReport();
  if (!result.ok) {
    return NextResponse.json({ error: result.error }, { status: 500 });
  }
  return NextResponse.json({ ok: true, points: buildRevenueTrend(result.report.items) });
}
