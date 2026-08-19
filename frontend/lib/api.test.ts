import { afterEach, describe, expect, it, vi } from "vitest";

import { createPlan, getPlans, getSubscriberStats, loadSubscriberStats } from "./api";

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

function mockFetch(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
  delete process.env.NETGRID_DEMO_TOKEN;
  delete process.env.BACKEND_URL;
});

describe("getSubscriberStats", () => {
  it("fetches with bearer auth and no-store caching, returning parsed stats", async () => {
    process.env.NETGRID_DEMO_TOKEN = "tok123";
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
    process.env.NETGRID_DEMO_TOKEN = "tok123";
    process.env.BACKEND_URL = "http://backend:8000";
    mockFetch({ ok: true, json: async () => STATS });

    await getSubscriberStats();

    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://backend:8000/api/v1/subscribers/stats",
      expect.anything(),
    );
  });

  it("throws when the token is missing", async () => {
    mockFetch({ ok: true, json: async () => STATS });
    await expect(getSubscriberStats()).rejects.toThrow("NETGRID_DEMO_TOKEN");
  });

  it("throws on a non-OK response", async () => {
    process.env.NETGRID_DEMO_TOKEN = "tok123";
    mockFetch({ ok: false, status: 403 });
    await expect(getSubscriberStats()).rejects.toThrow("HTTP 403");
  });
});

describe("loadSubscriberStats", () => {
  it("returns the stats on success", async () => {
    process.env.NETGRID_DEMO_TOKEN = "tok123";
    mockFetch({ ok: true, json: async () => STATS });
    await expect(loadSubscriberStats()).resolves.toEqual({ ok: true, stats: STATS });
  });

  it("returns an error result instead of throwing", async () => {
    process.env.NETGRID_DEMO_TOKEN = "tok123";
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
  };

  it("getPlans returns the items of the paginated response", async () => {
    process.env.NETGRID_DEMO_TOKEN = "tok123";
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
    process.env.NETGRID_DEMO_TOKEN = "tok123";
    mockFetch({ ok: true, status: 201, json: async () => PLAN });

    const created = await createPlan({ name: "Starter", price: "9.99" });
    expect(created).toEqual(PLAN);
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ name: "Starter", price: "9.99" });
  });

  it("maps a backend error envelope to ApiError", async () => {
    process.env.NETGRID_DEMO_TOKEN = "tok123";
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
