import { NextResponse } from "next/server";

import { ApiError, setAdminRoles } from "@/lib/api";

/**
 * BFF proxy for role assignment. The admin form (client) PUTs the full role
 * set here; the backend replaces the admin's roles and invalidates their
 * permission cache.
 */
export async function PUT(request: Request, { params }: { params: Promise<{ id: string }> }) {
  try {
    const { id } = await params;
    const payload = await request.json();
    const roleIds = (payload as { role_ids?: number[] }).role_ids;
    if (!Array.isArray(roleIds)) {
      return NextResponse.json({ error: "role_ids is required" }, { status: 400 });
    }
    const admin = await setAdminRoles(Number(id), roleIds);
    return NextResponse.json(admin);
  } catch (err) {
    if (err instanceof ApiError) {
      return NextResponse.json({ error: err.message }, { status: err.status });
    }
    const message = err instanceof Error ? err.message : "Unexpected error";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
