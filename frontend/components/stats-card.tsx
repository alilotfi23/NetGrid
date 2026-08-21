import { loadSubscriberStats } from "@/lib/api";
import { StatsCardClient } from "./stats-card-client";

/**
 * Dashboard card for subscriber counts. A server component: fetches the
 * backend server-side (token stays out of the browser) and hands the result
 * to the polling client as the initial render, so the first paint is instant
 * and the card then refreshes every 30s.
 */
export async function StatsCard() {
  const initial = await loadSubscriberStats();
  return <StatsCardClient initial={initial} />;
}
