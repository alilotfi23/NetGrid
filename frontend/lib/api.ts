/**
 * Server-side API helpers for the NetGrid dashboard.
 *
 * These run only in server components / route handlers: the backend requires
 * a bearer token, so the credential is read from the environment here and
 * never shipped to the browser. A real admin auth flow (login page, token
 * storage, refresh) arrives with Phase 12; NETGRID_DEMO_TOKEN is the dev
 * bootstrap until then.
 */

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
};

export function backendUrl(): string {
  return process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL;
}

export function demoToken(): string | undefined {
  return process.env.NETGRID_DEMO_TOKEN;
}

/** Fetch the backend with the server-side bearer token; throws ApiError on !ok. */
export async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const token = demoToken();
  if (!token) {
    throw new Error("NETGRID_DEMO_TOKEN is not configured");
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
