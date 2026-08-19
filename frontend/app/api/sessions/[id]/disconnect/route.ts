import { NextResponse } from "next/server";

import { ApiError, disconnectSession } from "@/lib/api";

/**
 * BFF proxy for the RFC 5176 disconnect action. The client button POSTs here;
 * this route handler calls FastAPI with the server-side session token, so the
 * cookie never reaches the browser.
 */
export async function POST(_request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    await disconnectSession(Number(id));
    return NextResponse.json({ status: "disconnected" });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
