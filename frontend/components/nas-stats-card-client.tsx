"use client";

import type { NasDevicesResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { NasStatsCardView } from "./nas-stats-card-view";

const REFRESH_MS = 30_000;

/**
 * Client half of the NAS summary card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so device counts stay live. Failed polls keep the last known
 * stats.
 */
export function NasStatsCardClient({ initial }: { initial: NasDevicesResult }) {
  const result = useLiveData<NasDevicesResult>("/api/dashboard/nas-stats", initial, REFRESH_MS);

  if (!result.ok) {
    return <NasStatsCardView error={result.error} />;
  }
  return <NasStatsCardView stats={result.stats} />;
}
