/**
 * Admin session helpers shared by the proxy, route handlers, and server-side
 * API fetchers. Pure (no next/server imports) so the decision logic is
 * unit-testable and the proxy can import it without bundling app code.
 *
 * The session lives in two HttpOnly cookies: a short-lived access token and a
 * rotating refresh token. Tokens are minted by FastAPI; the frontend only ever
 * stores and forwards them.
 */

export const ACCESS_COOKIE = "netgrid_access";
export const REFRESH_COOKIE = "netgrid_refresh";

export const ACCESS_TTL_SECONDS = 15 * 60; // matches backend access-token lifetime
export const REFRESH_TTL_SECONDS = 7 * 24 * 3600; // matches backend refresh-token lifetime

/** Refresh the access token when it has less than this much life left. */
export const EXPIRY_SKEW_SECONDS = 30;

export function cookieOptions(secure: boolean, maxAge: number) {
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    secure,
    path: "/",
    maxAge,
  };
}

/** Safely decode a JWT payload (base64url) without verifying the signature. */
export function decodeJwtPayload(token: string): { exp?: number } | null {
  const parts = token.split(".");
  if (parts.length < 2) return null;
  try {
    const base64 = parts[1].replace(/-/g, "+").replace(/_/g, "/");
    const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4);
    const raw = atob(padded);
    const text = new TextDecoder().decode(
      Uint8Array.from(raw, (c) => c.charCodeAt(0)),
    );
    const payload = JSON.parse(text) as unknown;
    if (typeof payload !== "object" || payload === null) return null;
    const exp = (payload as { exp?: unknown }).exp;
    return typeof exp === "number" ? { exp } : {};
  } catch {
    return null;
  }
}

/** True when the access token is missing, malformed, or past its expiry. */
export function isAccessTokenExpired(token: string | undefined, skewSeconds = EXPIRY_SKEW_SECONDS): boolean {
  if (!token) return true;
  const payload = decodeJwtPayload(token);
  if (!payload || typeof payload.exp !== "number") return true;
  return payload.exp * 1000 <= Date.now() + skewSeconds * 1000;
}

export type AuthDecision = { action: "allow" } | { action: "refresh" } | { action: "login" };

/**
 * What the proxy should do for a request with the given cookies:
 * - allow: a valid access token is present
 * - refresh: no/expired access token, but a refresh token exists — try to rotate
 * - login: no usable session at all — redirect to the login page
 */
export function authDecision(
  accessToken: string | undefined,
  refreshToken: string | undefined,
): AuthDecision {
  if (accessToken && !isAccessTokenExpired(accessToken)) {
    return { action: "allow" };
  }
  if (refreshToken) {
    return { action: "refresh" };
  }
  return { action: "login" };
}
