import { describe, expect, it } from "vitest";

import {
  ACCESS_COOKIE,
  authDecision,
  decodeJwtPayload,
  isAccessTokenExpired,
  REFRESH_COOKIE,
} from "./auth";

// exp = 2000000000 (2033) — far future
const FUTURE = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoyMDAwMDAwMDAwfQ.sig";
// exp = 1000000000 (2001) — long past
const PAST = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxMDAwMDAwMDAwfQ.sig";

function tokenWithExp(exp: number): string {
  const payload = btoa(JSON.stringify({ sub: "1", exp }));
  return `header.${payload.replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "")}.sig`;
}

describe("decodeJwtPayload", () => {
  it("decodes a valid payload", () => {
    expect(decodeJwtPayload(FUTURE)).toEqual({ exp: 2000000000 });
  });

  it("returns null for malformed tokens", () => {
    expect(decodeJwtPayload("")).toBeNull();
    expect(decodeJwtPayload("no-dots-here")).toBeNull();
    expect(decodeJwtPayload("a.b")).toBeNull(); // not valid base64 payload
    expect(decodeJwtPayload("a.!!!.c")).toBeNull();
  });

  it("handles a payload without an exp claim", () => {
    const payload = btoa(JSON.stringify({ sub: "1" }));
    expect(decodeJwtPayload(`h.${payload}.s`)).toEqual({});
  });
});

describe("isAccessTokenExpired", () => {
  it("treats missing tokens as expired", () => {
    expect(isAccessTokenExpired(undefined)).toBe(true);
    expect(isAccessTokenExpired("")).toBe(true);
  });

  it("treats malformed tokens as expired", () => {
    expect(isAccessTokenExpired("garbage")).toBe(true);
  });

  it("accepts a valid future token", () => {
    expect(isAccessTokenExpired(FUTURE)).toBe(false);
  });

  it("rejects an expired token", () => {
    expect(isAccessTokenExpired(PAST)).toBe(true);
  });

  it("applies the skew: a token expiring soon needs a refresh", () => {
    const expiringSoon = tokenWithExp(Math.floor(Date.now() / 1000) + 10);
    expect(isAccessTokenExpired(expiringSoon)).toBe(true);
    // but with no skew it is still valid
    expect(isAccessTokenExpired(expiringSoon, 0)).toBe(false);
  });
});

describe("authDecision", () => {
  it("allows a valid access token", () => {
    expect(authDecision(FUTURE, "refresh")).toEqual({ action: "allow" });
    expect(authDecision(FUTURE, undefined)).toEqual({ action: "allow" });
  });

  it("refreshes when the access token is gone or expired but a refresh token exists", () => {
    expect(authDecision(undefined, "refresh")).toEqual({ action: "refresh" });
    expect(authDecision(PAST, "refresh")).toEqual({ action: "refresh" });
  });

  it("sends to login when there is no session at all", () => {
    expect(authDecision(undefined, undefined)).toEqual({ action: "login" });
    expect(authDecision(PAST, undefined)).toEqual({ action: "login" });
  });

  it("exposes the cookie names used by the proxy and route handlers", () => {
    expect(ACCESS_COOKIE).toBe("netgrid_access");
    expect(REFRESH_COOKIE).toBe("netgrid_refresh");
  });
});
