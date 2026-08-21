"use client";

import type { NasDevicesResult } from "@/lib/api";
import { DASHBOARD_REFRESH_MS, useLiveData } from "@/lib/use-live-data";
import { NasStatsCardView } from "./nas-stats-card-view";
import { StaleNotice } from "./stale-notice";

/**
 * Client half of the NAS summary card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so device counts stay live. Failed polls keep the last known
 * stats and surface a subtle stale caption once they've been missing a
 * while.
 */
export function NasStatsCardClient({ initial }: { initial: NasDevicesResult }) {
  const { data: result, stale, lastUpdatedAt } = useLiveData<NasDevicesResult>(
    "/api/dashboard/nas-stats",
    initial,
    DASHBOARD_REFRESH_MS,
  );

  return (
    <>
      {result.ok ? <NasStatsCardView stats={result.stats} /> : <NasStatsCardView error={result.error} />}
      {result.ok && stale && <StaleNotice lastUpdatedAt={lastUpdatedAt} />}
    </>
  );
}
