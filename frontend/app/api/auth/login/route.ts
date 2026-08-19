import { NextResponse } from "next/server";

import { ACCESS_COOKIE, ACCESS_TTL_SECONDS, cookieOptions, REFRESH_COOKIE, REFRESH_TTL_SECONDS } from "@/lib/auth";
import { backendUrl } from "@/lib/api";

/**
 * BFF login: proxy the credentials to FastAPI, then store the returned tokens
 * in HttpOnly cookies. The tokens never reach client-side JavaScript; the
 * dashboard's server-side fetches read the access cookie.
 */
export async function POST(request: Request) {
  let payload: { username?: string; password?: string };
  try {
    payload = (await request.json()) as { username?: string; password?: string };
  } catch {
    return NextResponse.json({ error: "Invalid request body" }, { status: 400 });
  }
  if (!payload.username || !payload.password) {
    return NextResponse.json({ error: "Username and password are required" }, { status: 400 });
  }

  const res = await fetch(`${backendUrl()}/api/v1/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username: payload.username, password: payload.password }),
    cache: "no-store",
  });
  const body = (await res.json().catch(() => null)) as {
    access_token?: string;
    refresh_token?: string;
    admin?: unknown;
    error?: { message?: string };
  } | null;

  if (!res.ok || !body?.access_token || !body?.refresh_token) {
    const message =
      body?.error?.message ?? (res.status === 401 ? "Invalid username or password" : `Login failed (HTTP ${res.status})`);
    return NextResponse.json({ error: message }, { status: res.status === 401 ? 401 : res.status });
  }

  const secure = request.url.startsWith("https");
  const response = NextResponse.json({ admin: body.admin });
  response.cookies.set(ACCESS_COOKIE, body.access_token, cookieOptions(secure, ACCESS_TTL_SECONDS));
  response.cookies.set(REFRESH_COOKIE, body.refresh_token, cookieOptions(secure, REFRESH_TTL_SECONDS));
  return response;
}
