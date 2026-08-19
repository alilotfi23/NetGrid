import { NextResponse } from "next/server";

import { ApiError, rotateNasDeviceSecret } from "@/lib/api";

/**
 * BFF proxy for the dedicated secret-rotation action. The client form POSTs
 * here; this route handler calls FastAPI with the server-side token, so the
 * new secret never reaches the browser in cleartext beyond this one request.
 */
export async function POST(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const payload = (await request.json()) as { secret?: string };
    if (!payload.secret) {
      return NextResponse.json({ error: "New shared secret is required" }, { status: 400 });
    }
    const device = await rotateNasDeviceSecret(Number(id), payload.secret);
    return NextResponse.json(device);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
