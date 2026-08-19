import { NextResponse } from "next/server";

import { ApiError, updateSubscriber } from "@/lib/api";

/**
 * BFF proxy for subscriber updates (status, plan, profile fields). Client
 * forms PATCH here; the token stays server-side.
 */
export async function PATCH(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const payload = await request.json();
    const subscriber = await updateSubscriber(Number(id), payload);
    return NextResponse.json(subscriber);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
