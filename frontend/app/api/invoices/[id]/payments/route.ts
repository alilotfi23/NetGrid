import { NextResponse } from "next/server";

import { ApiError, recordPayment } from "@/lib/api";

/**
 * BFF proxy for recording payments. The payment form (client) POSTs here; the
 * route handler calls the backend with the server-side token.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  try {
    const { id } = await params;
    const payload = await request.json();
    const result = await recordPayment(Number(id), payload);
    return NextResponse.json(result, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
