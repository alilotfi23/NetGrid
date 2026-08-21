"use client";

import type { NasDevicesResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { NasTypeBreakdownView } from "./nas-type-breakdown-view";

const REFRESH_MS = 30_000;

/**
 * Client half of the by-NAS-type card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the same BFF route
 * handler as the NAS summary card every 30s. Failed polls keep the last
 * known breakdown.
 */
export function NasTypeBreakdownCardClient({ initial }: { initial: NasDevicesResult }) {
  const result = useLiveData<NasDevicesResult>("/api/dashboard/nas-stats", initial, REFRESH_MS);

  if (!result.ok) {
    return <NasTypeBreakdownView error={result.error} />;
  }
  return <NasTypeBreakdownView byType={result.stats.by_type} />;
}
