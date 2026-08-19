import { loadSubscriberStats } from "@/lib/api";
import { StatsCardView } from "./stats-card-view";

/**
 * Dashboard card for subscriber counts. A server component: fetches the
 * backend server-side (no CORS, token stays out of the browser) and renders
 * the presentational view with either data or an error state.
 */
export async function StatsCard() {
  const result = await loadSubscriberStats();
  if (!result.ok) {
    return <StatsCardView error={result.error} />;
  }
  return <StatsCardView stats={result.stats} />;
}
