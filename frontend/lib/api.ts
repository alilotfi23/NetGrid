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

export type PlanSubscriberCount = {
  plan_id: number | null;
  plan_name: string | null;
  count: number;
};

export type SubscriberStats = {
  active: number;
  suspended: number;
  expired: number;
  total: number;
  by_plan: PlanSubscriberCount[];
};

export function backendUrl(): string {
  return process.env.BACKEND_URL ?? DEFAULT_BACKEND_URL;
}

export function demoToken(): string | undefined {
  return process.env.NETGRID_DEMO_TOKEN;
}

export async function getSubscriberStats(): Promise<SubscriberStats> {
  const token = demoToken();
  if (!token) {
    throw new Error("NETGRID_DEMO_TOKEN is not configured");
  }
  const res = await fetch(`${backendUrl()}/api/v1/subscribers/stats`, {
    headers: { Authorization: `Bearer ${token}` },
    // the dashboard shows live counts — never cache across requests
    cache: "no-store",
  });
  if (!res.ok) {
    throw new Error(`subscriber stats request failed: HTTP ${res.status}`);
  }
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
