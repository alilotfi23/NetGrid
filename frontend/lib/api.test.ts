import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createPlan,
  createSubscriber,
  getPlans,
  getSubscriberStats,
  getSubscribers,
  loadSubscriberHistory,
  loadSubscribers,
  loadSubscriberSessions,
  loadSubscriberStats,
  updateSubscriber,
} from "./api";

const STATS = {
  active: 2,
  suspended: 1,
  expired: 1,
  total: 4,
  by_plan: [
    { plan_id: 1, plan_name: "Starter", count: 2 },
    { plan_id: null, plan_name: null, count: 2 },
  ],
};

// The session token comes from the HttpOnly cookie (see lib/auth.ts).
const { sessionCookie } = vi.hoisted((): { sessionCookie: { value: string | undefined } } => ({
  sessionCookie: { value: "tok123" },
}));

vi.mock("next/headers", () => ({
  cookies: async () => ({
    // next/headers cookies().get() returns { name, value } or undefined
    get: (name: string) =>
      name === "netgrid_access" && sessionCookie.value
        ? { name, value: sessionCookie.value }
        : undefined,
  }),
}));

function mockFetch(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
  sessionCookie.value = "tok123";
  delete process.env.BACKEND_URL;
});

describe("getSubscriberStats", () => {
  it("fetches with bearer auth and no-store caching, returning parsed stats", async () => {
    mockFetch({ ok: true, json: async () => STATS });

    const stats = await getSubscriberStats();

    expect(stats).toEqual(STATS);
    const fetchMock = vi.mocked(fetch);
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/subscribers/stats",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("uses BACKEND_URL when set", async () => {
    process.env.BACKEND_URL = "http://backend:8000";
    mockFetch({ ok: true, json: async () => STATS });

    await getSubscriberStats();

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://backend:8000/api/v1/subscribers/stats",
      expect.anything(),
    );
  });

  it("throws when there is no session cookie", async () => {
    sessionCookie.value = undefined;
    mockFetch({ ok: true, json: async () => STATS });
    await expect(getSubscriberStats()).rejects.toThrow("No active session");
  });

  it("throws on a non-OK response", async () => {
    mockFetch({ ok: false, status: 403 });
    await expect(getSubscriberStats()).rejects.toThrow("HTTP 403");
  });
});

describe("loadSubscriberStats", () => {
  it("returns the stats on success", async () => {
    mockFetch({ ok: true, json: async () => STATS });
    await expect(loadSubscriberStats()).resolves.toEqual({ ok: true, stats: STATS });
  });

  it("returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 401 });
    const result = await loadSubscriberStats();
    expect(result).toEqual({ ok: false, error: "request failed: HTTP 401" });
  });
});

describe("plan helpers", () => {
  const PLAN = {
    id: 1,
    name: "Starter",
    radius_group: "rad_starter",
    price: "9.99",
    duration_days: 30,
    bandwidth_down_mbps: 10,
    bandwidth_up_mbps: 5,
    quota_gb: 100,
    description: null,
    is_active: true,
    created_at: "2026-08-19T00:00:00",
    subscriber_count: 2,
  };

  it("getPlans returns the items of the paginated response", async () => {
    mockFetch({ ok: true, json: async () => ({ items: [PLAN], total: 1, page: 1, page_size: 20 }) });

    await expect(getPlans()).resolves.toEqual([PLAN]);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/plans",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("createPlan POSTs the payload and returns the created plan", async () => {
    mockFetch({ ok: true, status: 201, json: async () => PLAN });

    const created = await createPlan({ name: "Starter", price: "9.99" });
    expect(created).toEqual(PLAN);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Starter", price: "9.99" });
  });

  it("maps a backend error envelope to ApiError", async () => {
    mockFetch({
      ok: false,
      status: 409,
      json: async () => ({ error: { code: "CONFLICT", message: "Plan name or radius group already exists" } }),
    });

    await expect(createPlan({})).rejects.toMatchObject({
      name: "ApiError",
      status: 409,
      code: "CONFLICT",
      message: "Plan name or radius group already exists",
    });
  });
});

describe("subscriber helpers", () => {
  const SUBSCRIBER = {
    id: 7,
    username: "bob",
    full_name: "Bob Subscriber",
    email: "bob@netgrid.local",
    phone: null,
    status: "active",
    plan_id: 1,
    notes: null,
    created_at: "2026-08-19T00:00:00",
  };
  const HISTORY = [
    {
      id: 12,
      action: "update",
      metadata_: { fields: ["status"], status_from: "active", status_to: "suspended" },
      created_at: "2026-08-19T01:00:00",
    },
  ];
  const SESSION = {
    id: 3,
    username: "bob",
    nasipaddress: "192.168.0.10",
    acctstarttime: "2026-08-19T02:00:00Z",
    acctsessiontime: 3600,
    acctinputoctets: 1048576,
    acctoutputoctets: 2097152,
    framedipaddress: "10.0.0.5",
  };

  it("getSubscribers returns the paginated items", async () => {
    mockFetch({
      ok: true,
      json: async () => ({ items: [SUBSCRIBER], total: 1, page: 1, page_size: 100 }),
    });

    await expect(getSubscribers()).resolves.toEqual([SUBSCRIBER]);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/subscribers?page_size=100",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("loadSubscribers returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadSubscribers()).toEqual({
      ok: false,
      error: "request failed: HTTP 403",
    });
  });

  it("loadSubscriberHistory fetches the profile history endpoint", async () => {
    mockFetch({ ok: true, json: async () => HISTORY });

    expect(await loadSubscriberHistory(7)).toEqual({ ok: true, history: HISTORY });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/subscribers/7/history",
      expect.anything(),
    );
  });

  it("loadSubscriberSessions fetches the live sessions endpoint", async () => {
    mockFetch({ ok: true, json: async () => [SESSION] });

    expect(await loadSubscriberSessions(7)).toEqual({ ok: true, sessions: [SESSION] });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/subscribers/7/sessions",
      expect.anything(),
    );
  });

  it("loadSubscriberSessions surfaces backend errors", async () => {
    mockFetch({ ok: false, status: 404 });
    expect(await loadSubscriberSessions(999)).toEqual({
      ok: false,
      error: "request failed: HTTP 404",
    });
  });

  it("createSubscriber POSTs the payload and returns the created subscriber", async () => {
    mockFetch({ ok: true, status: 201, json: async () => SUBSCRIBER });

    const created = await createSubscriber({
      username: "bob",
      full_name: "Bob Subscriber",
      password: "radpass123",
      plan_id: 1,
    });
    expect(created).toEqual(SUBSCRIBER);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/subscribers");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      username: "bob",
      full_name: "Bob Subscriber",
      password: "radpass123",
      plan_id: 1,
    });
  });

  it("updateSubscriber PATCHes to the subscriber endpoint", async () => {
    mockFetch({ ok: true, json: async () => ({ ...SUBSCRIBER, status: "suspended" }) });

    const updated = await updateSubscriber(7, { status: "suspended" });
    expect(updated.status).toBe("suspended");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/subscribers/7");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ status: "suspended" });
  });
});
