"use client";

import type { NasDevicesResult } from "@/lib/api";
import { DASHBOARD_REFRESH_MS, useLiveData } from "@/lib/use-live-data";
import { NasTypeBreakdownView } from "./nas-type-breakdown-view";
import { StaleNotice } from "./stale-notice";

/**
 * Client half of the by-NAS-type card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the same BFF route
 * handler as the NAS summary card every 30s. Failed polls keep the last
 * known breakdown and surface a subtle stale caption once they've been
 * missing a while.
 */
export function NasTypeBreakdownCardClient({ initial }: { initial: NasDevicesResult }) {
  const { data: result, stale, lastUpdatedAt } = useLiveData<NasDevicesResult>(
    "/api/dashboard/nas-stats",
    initial,
    DASHBOARD_REFRESH_MS,
  );

  return (
    <>
      {result.ok ? (
        <NasTypeBreakdownView byType={result.stats.by_type} />
      ) : (
        <NasTypeBreakdownView error={result.error} />
      )}
      {result.ok && stale && <StaleNotice lastUpdatedAt={lastUpdatedAt} />}
    </>
  );
}
