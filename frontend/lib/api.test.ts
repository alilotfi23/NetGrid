import { afterEach, describe, expect, it, vi } from "vitest";

import {
  createAdmin,
  createNasDevice,
  createPlan,
  createRole,
  createSubscriber,
  deleteAdmin,
  deleteNasDevice,
  deleteRole,
  disconnectSession,
  generateInvoices,
  getAdmins,
  getInvoices,
  getMe,
  getNasDevices,
  getPaymentsReport,
  getPermissions,
  getPlans,
  getRoles,
  getSessions,
  getSubscriberStats,
  getSubscribers,
  loadAdmins,
  loadInvoice,
  loadInvoices,
  loadMe,
  loadNasDevice,
  loadNasDevices,
  loadPaymentsReport,
  loadRoles,
  loadSessions,
  loadSubscriberHistory,
  loadSubscribers,
  loadSubscriberSessions,
  loadSubscriberStats,
  recordPayment,
  rotateNasDeviceSecret,
  setAdminRoles,
  setRolePermissions,
  updateAdmin,
  updateNasDevice,
  updateRole,
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

describe("NAS device helpers", () => {
  const DEVICE = {
    id: 3,
    name: "edge-r1",
    ip_address: "192.168.0.10",
    shortname: "edge1",
    nas_type: "other",
    ports: 1812,
    server: null,
    community: null,
    description: "core router",
    is_active: true,
    created_at: "2026-08-19T00:00:00",
  };

  it("getNasDevices returns the paginated items plus global stats", async () => {
    mockFetch({
      ok: true,
      json: async () => ({
        items: [DEVICE],
        total: 1,
        page: 1,
        page_size: 100,
        stats: {
          total: 1,
          active: 1,
          inactive: 0,
          by_type: [{ nas_type: "mikrotik", count: 1 }],
        },
      }),
    });

    await expect(getNasDevices()).resolves.toEqual({
      devices: [DEVICE],
      stats: {
        total: 1,
        active: 1,
        inactive: 0,
        by_type: [{ nas_type: "mikrotik", count: 1 }],
      },
    });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/nas-devices?page_size=100",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("loadNasDevices returns devices and stats on success", async () => {
    mockFetch({
      ok: true,
      json: async () => ({
        items: [DEVICE],
        total: 1,
        page: 1,
        page_size: 100,
        stats: {
          total: 1,
          active: 1,
          inactive: 0,
          by_type: [{ nas_type: "mikrotik", count: 1 }],
        },
      }),
    });

    await expect(loadNasDevices()).resolves.toEqual({
      ok: true,
      devices: [DEVICE],
      stats: {
        total: 1,
        active: 1,
        inactive: 0,
        by_type: [{ nas_type: "mikrotik", count: 1 }],
      },
    });
  });

  it("getNasDevices passes the nas_type filter through to the API", async () => {
    mockFetch({
      ok: true,
      json: async () => ({
        items: [],
        total: 0,
        page: 1,
        page_size: 100,
        stats: { total: 0, active: 0, inactive: 0, by_type: [] },
      }),
    });

    await getNasDevices("mikrotik");
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/nas-devices?page_size=100&nas_type=mikrotik",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("getSubscribers passes plan_id and no_plan filters through to the API", async () => {
    mockFetch({ ok: true, json: async () => ({ items: [] }) });

    await getSubscribers({ planId: 3, noPlan: true });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/subscribers?page_size=100&plan_id=3&no_plan=1",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("loadNasDevices returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadNasDevices()).toEqual({
      ok: false,
      error: "request failed: HTTP 403",
    });
  });

  it("loadNasDevice fetches a single device by id", async () => {
    mockFetch({ ok: true, json: async () => DEVICE });

    expect(await loadNasDevice(3)).toEqual({ ok: true, device: DEVICE });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/nas-devices/3",
      expect.anything(),
    );
  });

  it("createNasDevice POSTs the payload with the secret and returns the device", async () => {
    mockFetch({ ok: true, status: 201, json: async () => DEVICE });

    const created = await createNasDevice({
      name: "edge-r1",
      ip_address: "192.168.0.10",
      shortname: "edge1",
      secret: "s3cret",
      is_active: true,
    });
    expect(created).toEqual(DEVICE);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/nas-devices");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      name: "edge-r1",
      ip_address: "192.168.0.10",
      shortname: "edge1",
      secret: "s3cret",
      is_active: true,
    });
  });

  it("updateNasDevice PATCHes to the device endpoint", async () => {
    mockFetch({ ok: true, json: async () => ({ ...DEVICE, is_active: false }) });

    const updated = await updateNasDevice(3, { is_active: false });
    expect(updated.is_active).toBe(false);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/nas-devices/3");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ is_active: false });
  });

  it("getSessions returns the paginated items plus session stats", async () => {
    mockFetch({
      ok: true,
      json: async () => ({
        items: [],
        total: 0,
        page: 1,
        page_size: 100,
        stats: { total: 0, by_nas: [] },
      }),
    });

    await expect(getSessions()).resolves.toEqual({
      sessions: [],
      stats: { total: 0, by_nas: [] },
    });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/sessions?page_size=100",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("loadSessions returns sessions and stats on success", async () => {
    mockFetch({
      ok: true,
      json: async () => ({
        items: [{ id: 1, username: "bob", subscriber_id: 7 }],
        total: 1,
        page: 1,
        page_size: 100,
        stats: {
          total: 1,
          by_nas: [{ nasipaddress: "192.168.0.10", count: 1, nas_shortname: "edge-r1" }],
        },
      }),
    });

    await expect(loadSessions()).resolves.toEqual({
      ok: true,
      sessions: [{ id: 1, username: "bob", subscriber_id: 7 }],
      stats: {
        total: 1,
        by_nas: [{ nasipaddress: "192.168.0.10", count: 1, nas_shortname: "edge-r1" }],
      },
    });
  });

  it("loadSessions returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadSessions()).toEqual({
      ok: false,
      error: "request failed: HTTP 403",
    });
  });

  it("disconnectSession POSTs to the session disconnect endpoint", async () => {
    mockFetch({ ok: true, json: async () => ({ status: "disconnected" }) });

    await disconnectSession(7);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/sessions/7/disconnect");
    expect(init?.method).toBe("POST");
  });

  it("deleteNasDevice DELETEs without a body", async () => {
    mockFetch({ ok: true, status: 204, json: async () => ({}) });

    await deleteNasDevice(3);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/nas-devices/3");
    expect(init?.method).toBe("DELETE");
  });

  it("rotateNasDeviceSecret POSTs the new secret to the rotate endpoint", async () => {
    mockFetch({ ok: true, json: async () => DEVICE });

    const rotated = await rotateNasDeviceSecret(3, "new-secret-99");
    expect(rotated).toEqual(DEVICE);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/nas-devices/3/rotate-secret");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ secret: "new-secret-99" });
  });
});

describe("invoice helpers", () => {
  const INVOICE = {
    id: 12,
    subscriber_id: 7,
    subscriber_username: "bob",
    plan_name: "Starter",
    period_start: "2026-03-01",
    period_end: "2026-03-30",
    amount: "10.00",
    status: "issued",
    issued_at: "2026-03-01T00:00:00",
    due_at: "2026-03-30",
    paid_at: null,
    payments: [],
  };
  const STATS = {
    issued: 1,
    paid: 0,
    overdue: 0,
    outstanding_amount: "10.00",
  };
  const REPORT = {
    items: [
      { month: "2026-03", method: "cash", revenue: "10.00", count: 1 },
      { month: "2026-02", method: "bank_transfer", revenue: "25.00", count: 1 },
    ],
    total_revenue: "35.00",
  };

  it("getInvoices returns the paginated items plus stats and page metadata", async () => {
    mockFetch({
      ok: true,
      json: async () => ({ items: [INVOICE], total: 42, page: 2, page_size: 20, stats: STATS }),
    });

    await expect(getInvoices()).resolves.toEqual({
      invoices: [INVOICE],
      stats: STATS,
      total: 42,
      page: 2,
      pageSize: 20,
    });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/invoices?page_size=20",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("getInvoices forwards page, page_size, and the status filter", async () => {
    mockFetch({ ok: true, json: async () => ({ items: [], total: 0, page: 1, page_size: 20, stats: STATS }) });

    await getInvoices({ status: "overdue", page: 3, pageSize: 50 });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/invoices?page_size=50&page=3&status=overdue",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("loadInvoices returns invoices, stats, and page metadata on success", async () => {
    mockFetch({
      ok: true,
      json: async () => ({ items: [INVOICE], total: 42, page: 2, page_size: 20, stats: STATS }),
    });

    await expect(loadInvoices({ page: 2 })).resolves.toEqual({
      ok: true,
      invoices: [INVOICE],
      stats: STATS,
      total: 42,
      page: 2,
      pageSize: 20,
    });
  });

  it("loadInvoices returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadInvoices()).toEqual({
      ok: false,
      error: "request failed: HTTP 403",
    });
  });

  it("loadInvoice fetches a single invoice by id", async () => {
    mockFetch({ ok: true, json: async () => INVOICE });

    expect(await loadInvoice(12)).toEqual({ ok: true, invoice: INVOICE });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/invoices/12",
      expect.anything(),
    );
  });

  it("getPaymentsReport fetches the report without a year param", async () => {
    mockFetch({ ok: true, json: async () => REPORT });

    await expect(getPaymentsReport()).resolves.toEqual(REPORT);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/invoices/report",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("getPaymentsReport passes the year filter through to the API", async () => {
    mockFetch({ ok: true, json: async () => REPORT });

    await getPaymentsReport(2026);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/invoices/report?year=2026",
      expect.anything(),
    );
  });

  it("loadPaymentsReport forwards the year filter", async () => {
    mockFetch({ ok: true, json: async () => REPORT });

    await expect(loadPaymentsReport(2025)).resolves.toEqual({ ok: true, report: REPORT });
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/invoices/report?year=2025",
      expect.anything(),
    );
  });

  it("loadPaymentsReport returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadPaymentsReport()).toEqual({
      ok: false,
      error: "request failed: HTTP 403",
    });
  });

  it("generateInvoices POSTs an empty payload to the generate endpoint", async () => {
    mockFetch({ ok: true, json: async () => ({ created: 3 }) });

    await expect(generateInvoices()).resolves.toEqual({ created: 3 });
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/invoices/generate");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({});
  });

  it("recordPayment POSTs the payment to the invoice endpoint", async () => {
    const payment = {
      id: 1,
      invoice_id: 12,
      amount: "10.00",
      method: "cash",
      reference: null,
      status: "completed",
      created_at: "2026-03-05T00:00:00",
    };
    mockFetch({
      ok: true,
      status: 201,
      json: async () => ({ payment, invoice: { ...INVOICE, status: "paid" } }),
    });

    const result = await recordPayment(12, { amount: "10.00", method: "cash" });
    expect(result.payment).toEqual(payment);
    expect(result.invoice.status).toBe("paid");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/invoices/12/payments");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ amount: "10.00", method: "cash" });
  });
});

describe("admin and role helpers", () => {
  const ROLE = {
    id: 6,
    name: "support_agent",
    description: "Customer support",
    permissions: [
      { id: 14, code: "subscribers:read", description: null },
      { id: 19, code: "invoices:read", description: null },
    ],
  };
  const ADMIN = {
    id: 2,
    username: "superadmin",
    email: "superadmin@netgrid.local",
    is_active: true,
    roles: [{ id: 3, name: "super_admin", description: null }],
  };
  const PERMISSIONS = [
    { id: 14, code: "subscribers:read", description: null },
    { id: 29, code: "*:*", description: null },
  ];

  it("getAdmins returns the paginated items", async () => {
    mockFetch({ ok: true, json: async () => ({ items: [ADMIN], total: 1, page: 1, page_size: 100 }) });

    await expect(getAdmins()).resolves.toEqual([ADMIN]);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/admins?page_size=100",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("loadAdmins returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadAdmins()).toEqual({ ok: false, error: "request failed: HTTP 403" });
  });

  it("getRoles returns the paginated items", async () => {
    mockFetch({ ok: true, json: async () => ({ items: [ROLE], total: 1, page: 1, page_size: 1 }) });

    await expect(getRoles()).resolves.toEqual([ROLE]);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/roles",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("loadRoles returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadRoles()).toEqual({ ok: false, error: "request failed: HTTP 403" });
  });

  it("getPermissions returns the catalog items", async () => {
    mockFetch({ ok: true, json: async () => ({ items: PERMISSIONS, total: 2, page: 1, page_size: 2 }) });

    await expect(getPermissions()).resolves.toEqual(PERMISSIONS);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/permissions",
      expect.objectContaining({
        headers: expect.objectContaining({ Authorization: "Bearer tok123" }),
        cache: "no-store",
      }),
    );
  });

  it("getMe fetches the current admin from /auth/me", async () => {
    mockFetch({ ok: true, json: async () => ADMIN });

    await expect(getMe()).resolves.toEqual(ADMIN);
    expect(vi.mocked(fetch)).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/auth/me",
      expect.anything(),
    );
  });

  it("loadMe returns an error result instead of throwing", async () => {
    mockFetch({ ok: false, status: 403 });
    expect(await loadMe()).toEqual({ ok: false, error: "request failed: HTTP 403" });
  });

  it("createAdmin POSTs the payload and returns the created admin", async () => {
    mockFetch({ ok: true, status: 201, json: async () => ADMIN });

    const created = await createAdmin({
      username: "superadmin",
      email: "superadmin@netgrid.local",
      password: "secret123",
      role_ids: [3],
    });
    expect(created).toEqual(ADMIN);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/admins");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      username: "superadmin",
      email: "superadmin@netgrid.local",
      password: "secret123",
      role_ids: [3],
    });
  });

  it("updateAdmin PATCHes to the admin endpoint", async () => {
    mockFetch({ ok: true, json: async () => ({ ...ADMIN, is_active: false }) });

    const updated = await updateAdmin(2, { is_active: false });
    expect(updated.is_active).toBe(false);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/admins/2");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ is_active: false });
  });

  it("setAdminRoles PUTs the full role set to the roles endpoint", async () => {
    mockFetch({ ok: true, json: async () => ADMIN });

    await setAdminRoles(2, [3]);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/admins/2/roles");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ role_ids: [3] });
  });

  it("deleteAdmin DELETEs without a body", async () => {
    mockFetch({ ok: true, status: 204, json: async () => ({}) });

    await deleteAdmin(2);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/admins/2");
    expect(init?.method).toBe("DELETE");
  });

  it("createRole POSTs the payload and returns the created role", async () => {
    mockFetch({ ok: true, status: 201, json: async () => ROLE });

    const created = await createRole({
      name: "support_agent",
      description: "Customer support",
      permission_codes: ["subscribers:read"],
    });
    expect(created).toEqual(ROLE);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/roles");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      name: "support_agent",
      description: "Customer support",
      permission_codes: ["subscribers:read"],
    });
  });

  it("updateRole PATCHes to the role endpoint", async () => {
    mockFetch({ ok: true, json: async () => ({ ...ROLE, name: "support" }) });

    const updated = await updateRole(6, { name: "support" });
    expect(updated.name).toBe("support");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/roles/6");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ name: "support" });
  });

  it("setRolePermissions PUTs the permission-code set", async () => {
    mockFetch({ ok: true, json: async () => ROLE });

    await setRolePermissions(6, ["subscribers:read"]);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/roles/6/permissions");
    expect(init?.method).toBe("PUT");
    expect(JSON.parse(String(init?.body))).toEqual({ permission_codes: ["subscribers:read"] });
  });

  it("deleteRole DELETEs without a body", async () => {
    mockFetch({ ok: true, status: 204, json: async () => ({}) });

    await deleteRole(6);
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("http://localhost:8000/api/v1/roles/6");
    expect(init?.method).toBe("DELETE");
  });
});
