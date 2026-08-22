"use client";

import type { UsageResult } from "@/lib/api";
import { DASHBOARD_REFRESH_MS, useLiveData } from "@/lib/use-live-data";

import { StaleNotice } from "./stale-notice";
import { UsageCardView } from "./usage-card-view";

/**
 * Client half of the data-cap usage card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so consumption stays live. Failed polls keep the last known
 * usage and surface a subtle stale caption once they've been missing a
 * while.
 */
export function UsageCardClient({ initial }: { initial: UsageResult }) {
  const { data: result, stale, lastUpdatedAt } = useLiveData<UsageResult>(
    "/api/dashboard/usage",
    initial,
    DASHBOARD_REFRESH_MS,
  );

  return (
    <>
      {result.ok ? <UsageCardView usage={result.usage} /> : <UsageCardView error={result.error} />}
      {result.ok && stale && <StaleNotice lastUpdatedAt={lastUpdatedAt} />}
    </>
  );
}
