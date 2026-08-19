import { NextResponse } from "next/server";

import { ApiError, generateInvoices } from "@/lib/api";

/**
 * BFF proxy: the Generate Invoices button (client) POSTs here; this route
 * handler calls POST /api/v1/invoices/generate with the server-side token.
 */
export async function POST(request: Request) {
  try {
    const payload = await request.json();
    const result = await generateInvoices(payload);
    return NextResponse.json(result);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
