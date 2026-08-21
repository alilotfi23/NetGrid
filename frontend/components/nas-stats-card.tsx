import { loadNasDevices } from "@/lib/api";
import { NasStatsCardClient } from "./nas-stats-card-client";

/**
 * Dashboard card for NAS device counts. A server component: fetches the
 * backend server-side (token stays out of the browser) and hands the result
 * to the polling client as the initial render, so the first paint is instant
 * and the card then refreshes every 30s.
 */
export async function NasStatsCard() {
  const initial = await loadNasDevices();
  return <NasStatsCardClient initial={initial} />;
}
