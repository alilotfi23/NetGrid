import { NextResponse } from "next/server";

import { ApiError, updatePlan } from "@/lib/api";

/**
 * BFF proxy for plan updates. Client forms PATCH here; the token stays
 * server-side.
 */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const payload = await request.json();
    const plan = await updatePlan(Number(id), payload);
    return NextResponse.json(plan);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
