import { NextResponse } from "next/server";

import { ApiError, createPlan } from "@/lib/api";

/**
 * BFF proxy: the plan form (client) POSTs here; this route handler calls the
 * FastAPI backend with the server-side token, so the credential never reaches
 * the browser.
 */
export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const plan = await createPlan(payload);
    return NextResponse.json(plan, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
