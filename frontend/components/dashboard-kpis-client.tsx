"use client";

import type { DashboardKpisResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { DashboardKpisView } from "./dashboard-kpis-view";
import { StaleNotice } from "./stale-notice";

const REFRESH_MS = 30_000;

/**
 * Client half of the dashboard KPI strip: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so operators see live numbers without reloading. Failed polls
 * keep the last known data and surface a subtle stale caption once they've
 * been missing a while.
 */
export function DashboardKpisClient({ initial }: { initial: DashboardKpisResult }) {
  const { data: result, stale, lastUpdatedAt } = useLiveData<DashboardKpisResult>(
    "/api/dashboard/kpis",
    initial,
    REFRESH_MS,
  );

  return (
    <>
      {result.ok ? <DashboardKpisView kpis={result.kpis} /> : <DashboardKpisView error={result.error} />}
      {result.ok && stale && <StaleNotice lastUpdatedAt={lastUpdatedAt} />}
    </>
  );
}
