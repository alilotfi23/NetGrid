import { NextResponse } from "next/server";

import { ApiError, setRolePermissions } from "@/lib/api";

/**
 * BFF proxy for permission assignment. The role form (client) PUTs the full
 * permission-code set here; the backend replaces the role's permissions and
 * invalidates every member's permission cache.
 */
export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const payload = await request.json();
    const codes = (payload as { permission_codes?: string[] }).permission_codes;
    if (!Array.isArray(codes)) {
      return NextResponse.json({ error: "permission_codes is required" }, { status: 400 });
    }
    const role = await setRolePermissions(Number(id), codes);
    return NextResponse.json(role);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
