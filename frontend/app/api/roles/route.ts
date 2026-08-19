import { NextResponse } from "next/server";

import { ApiError, createRole } from "@/lib/api";

/**
 * BFF proxy: the role form (client) POSTs here; this route handler calls the
 * FastAPI backend with the server-side token.
 */
export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const role = await createRole(payload);
    return NextResponse.json(role, { status: 201 });
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
