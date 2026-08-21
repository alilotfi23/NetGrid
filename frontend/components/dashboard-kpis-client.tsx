"use client";

import type { DashboardKpisResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { DashboardKpisView } from "./dashboard-kpis-view";

const REFRESH_MS = 30_000;

/**
 * Client half of the dashboard KPI strip: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so operators see live numbers without reloading. Failed polls
 * keep the last known data.
 */
export function DashboardKpisClient({ initial }: { initial: DashboardKpisResult }) {
  const result = useLiveData<DashboardKpisResult>("/api/dashboard/kpis", initial, REFRESH_MS);

  if (!result.ok) {
    return <DashboardKpisView error={result.error} />;
  }
  return <DashboardKpisView kpis={result.kpis} />;
}
