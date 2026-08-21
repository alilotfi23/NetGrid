"use client";

import type { StatsResult } from "@/lib/api";
import { DASHBOARD_REFRESH_MS, useLiveData } from "@/lib/use-live-data";
import { StaleNotice } from "./stale-notice";
import { StatsCardView } from "./stats-card-view";

/**
 * Client half of the subscriber-stats card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so subscriber counts stay live. Failed polls keep the last
 * known stats and surface a subtle stale caption once they've been missing
 * a while.
 */
export function StatsCardClient({ initial }: { initial: StatsResult }) {
  const { data: result, stale, lastUpdatedAt } = useLiveData<StatsResult>(
    "/api/dashboard/subscriber-stats",
    initial,
    DASHBOARD_REFRESH_MS,
  );

  return (
    <>
      {result.ok ? <StatsCardView stats={result.stats} /> : <StatsCardView error={result.error} />}
      {result.ok && stale && <StaleNotice lastUpdatedAt={lastUpdatedAt} />}
    </>
  );
}
