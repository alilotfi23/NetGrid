"use client";

import type { RevenueTrendResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { RevenueTrendView } from "./revenue-trend-view";

const REFRESH_MS = 30_000;

/**
 * Client half of the revenue-trend card: starts from the server-rendered
 * `initial` points (instant first paint) and polls the BFF route handler
 * every 30s so the chart stays current. Failed polls keep the last known
 * series.
 */
export function RevenueTrendCardClient({ initial }: { initial: RevenueTrendResult }) {
  const result = useLiveData<RevenueTrendResult>("/api/dashboard/revenue-trend", initial, REFRESH_MS);

  if (!result.ok) {
    return <RevenueTrendView error={result.error} />;
  }
  return <RevenueTrendView points={result.points} />;
}
