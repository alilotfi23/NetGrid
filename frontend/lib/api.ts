/**
 * Server-side API helpers for the NetGrid dashboard.
 *
 * These run only in server components / route handlers: the backend requires
 * a bearer token, so the credential is read from the admin session cookie
 * (set by the login flow) and never shipped to the browser.
 */

import { cookies } from "next/headers";

import type { RevenueTrendPoint } from "./revenue-trend";
import { ACCESS_COOKIE } from "./auth";

const DEFAULT_BACKEND_URL = "http://localhost:8000";

export class ApiError extends Error {
  readonly status: number;
  readonly code: string | undefined;

  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

export type PlanSubscriberCount = {
  plan_id: number | null;
  plan_name: string | null;
  count: number;
};

export type PlanStatusCount = {
  plan_id: number | null;
  plan_name: string | null;
  status: string;
  count: number;
};

export type SubscriberStats = {
  active: number;
  suspended: number;
  expired: number;
  total: number;
  by_plan: PlanSubscriberCount[];
  by_plan_status: PlanStatusCount[];
};

/**
 * The four headline numbers shown on the dashboard KPI strip. A `null`
 * metric means that resource's stats couldn't be loaded (e.g. the viewer
 * lacks its read permission) and the tile renders an em dash.
 */
export type DashboardKpis = {
  activeSubscribers: number | null;
  liveSessions: number | null;
  revenueYearToDate: string | null;
  overdueCount: number | null;
  overdueAmount: string | null;
};

export type DashboardKpisResult =
  | { ok: true; kpis: DashboardKpis }
  | { ok: false; error: string };

/** The trailing-12-month revenue series for the dashboard trend card. */
export type RevenueTrendResult =
  | { ok: true; points: RevenueTrendPoint[] }
  | { ok: false; error: string };

/** One plan-assigned subscriber's current-month consumption vs quota. */
export type UsageRow = {
  subscriber_id: number;
  username: string;
  full_name: string;
  plan_id: number;
  plan_name: string;
  quota_gb: number | null;
  window_start: string;
  window_end: string;
  input_octets: number;
  output_octets: number;
  total_octets: number;
  total_gb: number;
  session_count: number;
  pct_used: number | null;
};

export type UsageReportData = {
  items: UsageRow[];
  total: number;
  stats: { total_consumed_gb: number; over_quota_count: number };
};

export type UsageResult = { ok: true; usage: UsageReportData } | { ok: false; error: string };

export async function getUsage(): Promise<UsageReportData> {
  const res = await apiFetch("/api/v1/usage");
  return (await res.json()) as UsageReportData;
}

export async function loadUsage(): Promise<UsageResult> {
  try {
    return { ok: true, usage: await getUsage() };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export type Plan = {
  id: number;
  name: string;
  radius_group: string;
  price: string;
  duration_days: number;
  bandwidth_down_mbps: number;
  bandwidth_up_mbps: number;
  quota_gb: number | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
  subscriber_count: number;
};

export function backendUrl(): string {
  return process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL;
}

/** The admin session access token from the HttpOnly cookie. */
export async function getSessionToken(): Promise<string | undefined> {
  const cookieStore = await cookies();
  return cookieStore.get(ACCESS_COOKIE)?.value;
}

/** Fetch the backend with the session bearer token; throws ApiError on !ok. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = await getSessionToken();
  if (!token) {
    throw new Error("No active session — log in first");
  }
  const res = await fetch(`${backendUrl()}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...init?.headers,
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let message = `request failed: HTTP ${res.status}`;
    let code: string | undefined;
    try {
      const body = (await res.json()) as { error?: { code?: string; message?: string } };
      if (body.error?.message) {
        message = body.error.message;
      }
      if (body.error?.code) {
        code = body.error.code;
      }
    } catch {
      // non-JSON error body — keep the fallback message
    }
    throw new ApiError(message, res.status, code);
  }
  return res;
}

export async function getSubscriberStats(): Promise<SubscriberStats> {
  const res = await apiFetch("/api/v1/subscribers/stats");
  return (await res.json()) as SubscriberStats;
}

export type StatsResult =
  | { ok: true; stats: SubscriberStats }
  | { ok: false; error: string };

/**
 * Load stats without throwing, so components can branch on the result instead
 * of try/catching (components handle render errors via error boundaries).
 */
export async function loadSubscriberStats(): Promise<StatsResult> {
  try {
    return { ok: true, stats: await getSubscriberStats() };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getPlans(): Promise<Plan[]> {
  const res = await apiFetch("/api/v1/plans");
  const page = (await res.json()) as { items: Plan[] };
  return page.items;
}

export type PlansResult = { ok: true; plans: Plan[] } | { ok: false; error: string };

export async function loadPlans(): Promise<PlansResult> {
  try {
    return { ok: true, plans: await getPlans() };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getPlan(id: number): Promise<Plan> {
  const res = await apiFetch(`/api/v1/plans/${id}`);
  return (await res.json()) as Plan;
}

export type PlanResult = { ok: true; plan: Plan } | { ok: false; error: string };

export async function loadPlan(id: number): Promise<PlanResult> {
  try {
    return { ok: true, plan: await getPlan(id) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/** Mutations — called from route handlers (never from the browser directly). */
export async function createPlan(payload: unknown): Promise<Plan> {
  const res = await apiFetch("/api/v1/plans", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Plan;
}

export async function updatePlan(id: number, payload: unknown): Promise<Plan> {
  const res = await apiFetch(`/api/v1/plans/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Plan;
}

export type Subscriber = {
  id: number;
  username: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  status: string;
  plan_id: number | null;
  notes: string | null;
  created_at: string;
};

export type SubscriberHistoryEntry = {
  id: number;
  action: string;
  metadata_: { fields?: string[]; status_from?: string; status_to?: string; username?: string } | null;
  created_at: string;
};

export type LiveSession = {
  id: number;
  username: string | null;
  nasipaddress: string | null;
  nas_shortname: string | null;
  subscriber_id: number | null;
  acctstarttime: string | null;
  acctsessiontime: number | null;
  acctinputoctets: number | null;
  acctoutputoctets: number | null;
  framedipaddress: string | null;
};

export async function getSubscribers(
  filters?: { planId?: number; noPlan?: boolean },
): Promise<Subscriber[]> {
  const params = new URLSearchParams({ page_size: "100" });
  if (filters?.planId != null) params.set("plan_id", String(filters.planId));
  if (filters?.noPlan) params.set("no_plan", "1");
  const res = await apiFetch(`/api/v1/subscribers?${params.toString()}`);
  const page = (await res.json()) as { items: Subscriber[] };
  return page.items;
}

export type SubscribersResult =
  | { ok: true; subscribers: Subscriber[] }
  | { ok: false; error: string };

export async function loadSubscribers(
  filters?: { planId?: number; noPlan?: boolean },
): Promise<SubscribersResult> {
  try {
    return { ok: true, subscribers: await getSubscribers(filters) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getSubscriber(id: number): Promise<Subscriber> {
  const res = await apiFetch(`/api/v1/subscribers/${id}`);
  return (await res.json()) as Subscriber;
}

export type SubscriberResult = { ok: true; subscriber: Subscriber } | { ok: false; error: string };

export async function loadSubscriber(id: number): Promise<SubscriberResult> {
  try {
    return { ok: true, subscriber: await getSubscriber(id) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getSubscriberHistory(id: number): Promise<SubscriberHistoryEntry[]> {
  const res = await apiFetch(`/api/v1/subscribers/${id}/history`);
  return (await res.json()) as SubscriberHistoryEntry[];
}

export type SubscriberHistoryResult =
  | { ok: true; history: SubscriberHistoryEntry[] }
  | { ok: false; error: string };

export async function loadSubscriberHistory(id: number): Promise<SubscriberHistoryResult> {
  try {
    return { ok: true, history: await getSubscriberHistory(id) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getSubscriberSessions(id: number): Promise<LiveSession[]> {
  const res = await apiFetch(`/api/v1/subscribers/${id}/sessions`);
  return (await res.json()) as LiveSession[];
}

export type SessionNasCount = {
  nasipaddress: string;
  count: number;
  nas_shortname: string | null;
};

export type SessionStats = {
  total: number;
  by_nas: SessionNasCount[];
};

export async function getSessions(): Promise<{ sessions: LiveSession[]; stats: SessionStats }> {
  const res = await apiFetch("/api/v1/sessions?page_size=100");
  const page = (await res.json()) as { items: LiveSession[]; stats: SessionStats };
  return { sessions: page.items, stats: page.stats };
}

export type SessionsResult =
  | { ok: true; sessions: LiveSession[]; stats: SessionStats }
  | { ok: false; error: string };

export async function loadSessions(): Promise<SessionsResult> {
  try {
    const { sessions, stats } = await getSessions();
    return { ok: true, sessions, stats };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/** Send an RFC 5176 Disconnect-Request to the session's NAS via the API. */
export async function disconnectSession(id: number): Promise<void> {
  await apiFetch(`/api/v1/sessions/${id}/disconnect`, { method: "POST" });
}

/** Mutations — called from route handlers (never from the browser directly). */
export async function createSubscriber(payload: unknown): Promise<Subscriber> {
  const res = await apiFetch("/api/v1/subscribers", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Subscriber;
}

export async function updateSubscriber(id: number, payload: unknown): Promise<Subscriber> {
  const res = await apiFetch(`/api/v1/subscribers/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Subscriber;
}

export type SubscriberSessionsResult =
  | { ok: true; sessions: LiveSession[] }
  | { ok: false; error: string };

export async function loadSubscriberSessions(id: number): Promise<SubscriberSessionsResult> {
  try {
    return { ok: true, sessions: await getSubscriberSessions(id) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/** One calendar month of a subscriber's radacct consumption (profile view). */
export type SubscriberUsageMonth = {
  month: string; // "YYYY-MM"
  start: string;
  end: string;
  input_octets: number;
  output_octets: number;
  total_octets: number;
  total_gb: number;
  session_count: number;
  quota_gb: number | null;
  pct_used: number | null;
};

export async function getSubscriberUsage(
  id: number,
  months = 12,
): Promise<SubscriberUsageMonth[]> {
  const res = await apiFetch(`/api/v1/subscribers/${id}/usage?months=${months}`);
  return (await res.json()) as SubscriberUsageMonth[];
}

export type SubscriberUsageResult =
  | { ok: true; months: SubscriberUsageMonth[] }
  | { ok: false; error: string };

export async function loadSubscriberUsage(
  id: number,
  months = 12,
): Promise<SubscriberUsageResult> {
  try {
    return { ok: true, months: await getSubscriberUsage(id, months) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export type NasDevice = {
  id: number;
  name: string;
  ip_address: string;
  shortname: string;
  nas_type: string;
  ports: number | null;
  server: string | null;
  community: string | null;
  description: string | null;
  is_active: boolean;
  created_at: string;
};

export type NasDeviceTypeCount = {
  nas_type: string;
  count: number;
};

export type NasDeviceStats = {
  total: number;
  active: number;
  inactive: number;
  by_type: NasDeviceTypeCount[];
};

export async function getNasDevices(
  nasType?: string,
): Promise<{ devices: NasDevice[]; stats: NasDeviceStats }> {
  const params = new URLSearchParams({ page_size: "100" });
  if (nasType) params.set("nas_type", nasType);
  const res = await apiFetch(`/api/v1/nas-devices?${params.toString()}`);
  const page = (await res.json()) as { items: NasDevice[]; stats: NasDeviceStats };
  return { devices: page.items, stats: page.stats };
}

export type NasDevicesResult =
  | { ok: true; devices: NasDevice[]; stats: NasDeviceStats }
  | { ok: false; error: string };

export async function loadNasDevices(nasType?: string): Promise<NasDevicesResult> {
  try {
    const { devices, stats } = await getNasDevices(nasType);
    return { ok: true, devices, stats };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getNasDevice(id: number): Promise<NasDevice> {
  const res = await apiFetch(`/api/v1/nas-devices/${id}`);
  return (await res.json()) as NasDevice;
}

export type NasDeviceResult = { ok: true; device: NasDevice } | { ok: false; error: string };

export async function loadNasDevice(id: number): Promise<NasDeviceResult> {
  try {
    return { ok: true, device: await getNasDevice(id) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/** Mutations — called from route handlers (never from the browser directly). */
export async function createNasDevice(payload: unknown): Promise<NasDevice> {
  const res = await apiFetch("/api/v1/nas-devices", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as NasDevice;
}

export async function updateNasDevice(id: number, payload: unknown): Promise<NasDevice> {
  const res = await apiFetch(`/api/v1/nas-devices/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as NasDevice;
}

export async function deleteNasDevice(id: number): Promise<void> {
  await apiFetch(`/api/v1/nas-devices/${id}`, { method: "DELETE" });
}

/** Rotate the shared secret without touching any other device field. */
export async function rotateNasDeviceSecret(id: number, secret: string): Promise<NasDevice> {
  const res = await apiFetch(`/api/v1/nas-devices/${id}/rotate-secret`, {
    method: "POST",
    body: JSON.stringify({ secret }),
  });
  return (await res.json()) as NasDevice;
}

export type Payment = {
  id: number;
  invoice_id: number;
  amount: string;
  method: string;
  reference: string | null;
  status: string;
  created_at: string;
};

export type Invoice = {
  id: number;
  subscriber_id: number;
  subscriber_username: string | null;
  plan_name: string;
  period_start: string;
  period_end: string;
  amount: string;
  status: string;
  issued_at: string;
  due_at: string;
  paid_at: string | null;
  payments: Payment[];
};

export type InvoiceStats = {
  issued: number;
  paid: number;
  overdue: number;
  outstanding_amount: string;
  overdue_amount: string;
};

export type PaymentReportRow = {
  month: string;
  method: string;
  revenue: string;
  count: number;
};

export type PaymentReport = {
  items: PaymentReportRow[];
  total_revenue: string;
};

export type InvoiceListFilters = {
  status?: string;
  page?: number;
  pageSize?: number;
};

export type InvoicePage = {
  invoices: Invoice[];
  stats: InvoiceStats;
  total: number;
  page: number;
  pageSize: number;
};

export async function getInvoices(filters?: InvoiceListFilters): Promise<InvoicePage> {
  const params = new URLSearchParams({ page_size: String(filters?.pageSize ?? 20) });
  if (filters?.page != null) params.set("page", String(filters.page));
  if (filters?.status) params.set("status", filters.status);
  const res = await apiFetch(`/api/v1/invoices?${params.toString()}`);
  const page = (await res.json()) as {
    items: Invoice[];
    stats: InvoiceStats;
    total: number;
    page: number;
    page_size: number;
  };
  return {
    invoices: page.items,
    stats: page.stats,
    total: page.total,
    page: page.page,
    pageSize: page.page_size,
  };
}

export type InvoicesResult =
  | ({ ok: true } & InvoicePage)
  | { ok: false; error: string };

export async function loadInvoices(filters?: InvoiceListFilters): Promise<InvoicesResult> {
  try {
    const { invoices, stats, total, page, pageSize } = await getInvoices(filters);
    return { ok: true, invoices, stats, total, page, pageSize };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getInvoice(id: number): Promise<Invoice> {
  const res = await apiFetch(`/api/v1/invoices/${id}`);
  return (await res.json()) as Invoice;
}

export type InvoiceResult = { ok: true; invoice: Invoice } | { ok: false; error: string };

export async function loadInvoice(id: number): Promise<InvoiceResult> {
  try {
    return { ok: true, invoice: await getInvoice(id) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getPaymentsReport(year?: number): Promise<PaymentReport> {
  const params = new URLSearchParams();
  if (year != null) params.set("year", String(year));
  const qs = params.toString();
  const res = await apiFetch(`/api/v1/invoices/report${qs ? `?${qs}` : ""}`);
  return (await res.json()) as PaymentReport;
}

export type PaymentsReportResult =
  | { ok: true; report: PaymentReport }
  | { ok: false; error: string };

export async function loadPaymentsReport(year?: number): Promise<PaymentsReportResult> {
  try {
    return { ok: true, report: await getPaymentsReport(year) };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/** Manually run the monthly invoice job (idempotent). */
export async function generateInvoices(payload?: unknown): Promise<{ created: number }> {
  const res = await apiFetch("/api/v1/invoices/generate", {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
  return (await res.json()) as { created: number };
}

/** Record a completed payment against an invoice; flips it to paid when done. */
export async function recordPayment(
  invoiceId: number,
  payload: unknown,
): Promise<{ payment: Payment; invoice: Invoice }> {
  const res = await apiFetch(`/api/v1/invoices/${invoiceId}/payments`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as { payment: Payment; invoice: Invoice };
}

export type RoleBrief = {
  id: number;
  name: string;
  description: string | null;
};

export type Admin = {
  id: number;
  username: string;
  email: string;
  is_active: boolean;
  roles: RoleBrief[];
};

export type Permission = {
  id: number;
  code: string;
  description: string | null;
};

export type Role = {
  id: number;
  name: string;
  description: string | null;
  permissions: Permission[];
};

export async function getAdmins(): Promise<Admin[]> {
  const res = await apiFetch("/api/v1/admins?page_size=100");
  const page = (await res.json()) as { items: Admin[] };
  return page.items;
}

export type AdminsResult = { ok: true; admins: Admin[] } | { ok: false; error: string };

export async function loadAdmins(): Promise<AdminsResult> {
  try {
    return { ok: true, admins: await getAdmins() };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getRoles(): Promise<Role[]> {
  const res = await apiFetch("/api/v1/roles");
  const page = (await res.json()) as { items: Role[] };
  return page.items;
}

export type RolesResult = { ok: true; roles: Role[] } | { ok: false; error: string };

export async function loadRoles(): Promise<RolesResult> {
  try {
    return { ok: true, roles: await getRoles() };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

export async function getPermissions(): Promise<Permission[]> {
  const res = await apiFetch("/api/v1/permissions");
  const page = (await res.json()) as { items: Permission[] };
  return page.items;
}

export type PermissionsResult =
  | { ok: true; permissions: Permission[] }
  | { ok: false; error: string };

export async function loadPermissions(): Promise<PermissionsResult> {
  try {
    return { ok: true, permissions: await getPermissions() };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/** The current admin (from /auth/me) — requires admins:read. */
export async function getMe(): Promise<Admin> {
  const res = await apiFetch("/api/v1/auth/me");
  return (await res.json()) as Admin;
}

export type MeResult = { ok: true; me: Admin } | { ok: false; error: string };

export async function loadMe(): Promise<MeResult> {
  try {
    return { ok: true, me: await getMe() };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/** Mutations — called from route handlers (never from the browser directly). */
export async function createAdmin(payload: unknown): Promise<Admin> {
  const res = await apiFetch("/api/v1/admins", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Admin;
}

export async function updateAdmin(id: number, payload: unknown): Promise<Admin> {
  const res = await apiFetch(`/api/v1/admins/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Admin;
}

export async function setAdminRoles(id: number, roleIds: number[]): Promise<Admin> {
  const res = await apiFetch(`/api/v1/admins/${id}/roles`, {
    method: "PUT",
    body: JSON.stringify({ role_ids: roleIds }),
  });
  return (await res.json()) as Admin;
}

export async function deleteAdmin(id: number): Promise<void> {
  await apiFetch(`/api/v1/admins/${id}`, { method: "DELETE" });
}

export async function createRole(payload: unknown): Promise<Role> {
  const res = await apiFetch("/api/v1/roles", {
    method: "POST",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Role;
}

export async function updateRole(id: number, payload: unknown): Promise<Role> {
  const res = await apiFetch(`/api/v1/roles/${id}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  return (await res.json()) as Role;
}

export async function setRolePermissions(id: number, codes: string[]): Promise<Role> {
  const res = await apiFetch(`/api/v1/roles/${id}/permissions`, {
    method: "PUT",
    body: JSON.stringify({ permission_codes: codes }),
  });
  return (await res.json()) as Role;
}

export async function deleteRole(id: number): Promise<void> {
  await apiFetch(`/api/v1/roles/${id}`, { method: "DELETE" });
}

export type AuditLogEntry = {
  id: number;
  admin_id: number | null;
  admin_username: string | null;
  action: string;
  resource: string;
  resource_id: string | null;
  metadata_: Record<string, unknown> | null;
  created_at: string;
};

export type AuditActorOption = {
  id: number;
  username: string;
};

export type AuditLogFilters = {
  actions: string[];
  resources: string[];
  admins: AuditActorOption[];
};

export type AuditLogListFilters = {
  adminId?: number;
  action?: string;
  resource?: string;
  page?: number;
  pageSize?: number;
};

export type AuditLogPage = {
  entries: AuditLogEntry[];
  filters: AuditLogFilters;
  total: number;
  page: number;
  pageSize: number;
};

export async function getAuditLogs(filters?: AuditLogListFilters): Promise<AuditLogPage> {
  const params = new URLSearchParams({ page_size: String(filters?.pageSize ?? 20) });
  if (filters?.page != null) params.set("page", String(filters.page));
  if (filters?.adminId != null) params.set("admin_id", String(filters.adminId));
  if (filters?.action) params.set("action", filters.action);
  if (filters?.resource) params.set("resource", filters.resource);
  const res = await apiFetch(`/api/v1/audit-logs?${params.toString()}`);
  const body = (await res.json()) as {
    items: AuditLogEntry[];
    filters: AuditLogFilters;
    total: number;
    page: number;
    page_size: number;
  };
  return {
    entries: body.items,
    filters: body.filters,
    total: body.total,
    page: body.page,
    pageSize: body.page_size,
  };
}

export type AuditLogsResult =
  | ({ ok: true } & AuditLogPage)
  | { ok: false; error: string };

export async function loadAuditLogs(filters?: AuditLogListFilters): Promise<AuditLogsResult> {
  try {
    const { entries, filters: options, total, page, pageSize } = await getAuditLogs(filters);
    return { ok: true, entries, filters: options, total, page, pageSize };
  } catch (err) {
    return { ok: false, error: err instanceof Error ? err.message : "Unknown error" };
  }
}

/**
 * Load the four dashboard KPI metrics from the backend in parallel. Each
 * metric loads independently, so a viewer lacking one resource's read
 * permission gets nulls for that metric rather than the whole strip failing;
 * only when every metric fails is the result an error.
 */
export async function loadDashboardKpis(): Promise<DashboardKpisResult> {
  const [subscribers, sessions, report, overdue] = await Promise.all([
    loadSubscriberStats(),
    loadSessions(),
    loadPaymentsReport(new Date().getFullYear()),
    loadInvoices({ status: "overdue", pageSize: 1 }),
  ]);

  const errors = [
    subscribers.ok ? null : subscribers.error,
    sessions.ok ? null : sessions.error,
    report.ok ? null : report.error,
    overdue.ok ? null : overdue.error,
  ];
  const firstError = errors.find((err): err is string => Boolean(err));

  if (!subscribers.ok && !sessions.ok && !report.ok && !overdue.ok) {
    return { ok: false, error: firstError ?? "Dashboard stats unavailable" };
  }

  return {
    ok: true,
    kpis: {
      activeSubscribers: subscribers.ok ? subscribers.stats.active : null,
      liveSessions: sessions.ok ? sessions.stats.total : null,
      revenueYearToDate: report.ok ? report.report.total_revenue : null,
      overdueCount: overdue.ok ? overdue.total : null,
      overdueAmount: overdue.ok ? overdue.stats.overdue_amount : null,
    },
  };
}
