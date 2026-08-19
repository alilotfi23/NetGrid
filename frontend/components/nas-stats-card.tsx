import { loadNasDevices } from "@/lib/api";
import { NasStatsCardView } from "./nas-stats-card-view";

/**
 * Dashboard card for NAS device counts. A server component: fetches the
 * backend server-side (token stays out of the browser) and renders the
 * presentational view with either data or an error state.
 */
export async function NasStatsCard() {
  const result = await loadNasDevices();
  if (!result.ok) {
    return <NasStatsCardView error={result.error} />;
  }
  return <NasStatsCardView stats={result.stats} />;
}
