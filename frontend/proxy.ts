import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

import {
  ACCESS_COOKIE,
  ACCESS_TTL_SECONDS,
  authDecision,
  cookieOptions,
  REFRESH_COOKIE,
  REFRESH_TTL_SECONDS,
} from "@/lib/auth";

/**
 * Session guard for the dashboard (Next 16 proxy, Node runtime).
 *
 * Every page except /login requires a session cookie. The access token lives
 * only 15 minutes, so when it is missing or near expiry but a refresh token
 * exists, the proxy rotates both tokens against FastAPI before the page
 * renders — the browser never sees the 401/redirect cycle. When no session
 * exists, the user is sent to /login.
 *
 * BFF route handlers under /api/auth/* are exempt (login/logout must work
 * without a session); all other /api/* routes stay protected so mutations
 * without a session never reach the backend.
 */
export async function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl;
  if (pathname === "/login" || pathname.startsWith("/api/auth")) {
    return NextResponse.next();
  }

  const accessToken = request.cookies.get(ACCESS_COOKIE)?.value;
  const refreshToken = request.cookies.get(REFRESH_COOKIE)?.value;
  const decision = authDecision(accessToken, refreshToken);

  if (decision.action === "allow") {
    return NextResponse.next();
  }

  const secure = request.nextUrl.protocol === "https:";
  if (decision.action === "login") {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  // refresh: rotate both tokens, then continue with fresh cookies
  const pair = await refreshTokens(refreshToken as string);
  if (!pair) {
    const toLogin = NextResponse.redirect(new URL("/login", request.url));
    toLogin.cookies.delete(ACCESS_COOKIE);
    toLogin.cookies.delete(REFRESH_COOKIE);
    return toLogin;
  }
  const response = NextResponse.next();
  response.cookies.set(ACCESS_COOKIE, pair.access, cookieOptions(secure, ACCESS_TTL_SECONDS));
  response.cookies.set(REFRESH_COOKIE, pair.refresh, cookieOptions(secure, REFRESH_TTL_SECONDS));
  return response;
}

async function refreshTokens(
  refreshToken: string,
): Promise<{ access: string; refresh: string } | null> {
  const backendUrl = process.env.BACKEND_URL ?? "http://localhost:8000";
  try {
    const res = await fetch(`${backendUrl}/api/v1/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refreshToken }),
      cache: "no-store",
    });
    if (!res.ok) return null;
    const body = (await res.json()) as { access_token?: string; refresh_token?: string };
    if (!body.access_token || !body.refresh_token) return null;
    return { access: body.access_token, refresh: body.refresh_token };
  } catch {
    return null;
  }
}

export const config = {
  // everything except static assets; /login and /api/auth/* are exempted above
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
