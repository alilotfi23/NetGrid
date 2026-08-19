import { NextResponse } from "next/server";

import { ApiError, createNasDevice } from "@/lib/api";

/**
 * BFF proxy: the NAS device form (client) POSTs here; this route handler calls
 * the FastAPI backend with the server-side token, so the shared secret never
 * reaches the browser.
 */
export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const device = await createNasDevice(payload);
    return NextResponse.json(device, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
