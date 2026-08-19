import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { ACCESS_COOKIE, REFRESH_COOKIE } from "@/lib/auth";
import { backendUrl } from "@/lib/api";

/**
 * BFF logout: revoke the refresh token server-side (the backend blacklists
 * its jti), then clear the session cookies.
 */
export async function POST() {
  const cookieStore = await cookies();
  const refreshToken = cookieStore.get(REFRESH_COOKIE)?.value;

  if (refreshToken) {
    try {
      await fetch(`${backendUrl()}/api/v1/auth/logout`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
        cache: "no-store",
      });
    } catch {
      // backend unreachable — still clear the local session cookies
    }
  }

  const response = NextResponse.json({ ok: true });
  response.cookies.delete(ACCESS_COOKIE);
  response.cookies.delete(REFRESH_COOKIE);
  return response;
}
