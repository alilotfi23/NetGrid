"use client";

import type { StatsResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { StatsCardView } from "./stats-card-view";

const REFRESH_MS = 30_000;

/**
 * Client half of the subscriber-stats card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so subscriber counts stay live. Failed polls keep the last
 * known stats.
 */
export function StatsCardClient({ initial }: { initial: StatsResult }) {
  const result = useLiveData<StatsResult>("/api/dashboard/subscriber-stats", initial, REFRESH_MS);

  if (!result.ok) {
    return <StatsCardView error={result.error} />;
  }
  return <StatsCardView stats={result.stats} />;
}
