"use client";

import type { RevenueTrendResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { RevenueTrendView } from "./revenue-trend-view";
import { StaleNotice } from "./stale-notice";

const REFRESH_MS = 30_000;

/**
 * Client half of the revenue-trend card: starts from the server-rendered
 * `initial` points (instant first paint) and polls the BFF route handler
 * every 30s so the chart stays current. Failed polls keep the last known
 * series and surface a subtle stale caption once they've been missing a
 * while.
 */
export function RevenueTrendCardClient({ initial }: { initial: RevenueTrendResult }) {
  const { data: result, stale, lastUpdatedAt } = useLiveData<RevenueTrendResult>(
    "/api/dashboard/revenue-trend",
    initial,
    REFRESH_MS,
  );

  return (
    <>
      {result.ok ? (
        <RevenueTrendView points={result.points} />
      ) : (
        <RevenueTrendView error={result.error} />
      )}
      {result.ok && stale && <StaleNotice lastUpdatedAt={lastUpdatedAt} />}
    </>
  );
}
