import { loadUsage } from "@/lib/api";

import { UsageCardClient } from "./usage-card-client";

/**
 * Dashboard card for data-cap usage (consumed GB vs plan quota). A server
 * component: fetches the backend server-side (token stays out of the
 * browser) and hands the result to the polling client as the initial
 * render, so the first paint is instant and the card then refreshes every
 * 30s.
 */
export async function UsageCard() {
  const initial = await loadUsage();
  return <UsageCardClient initial={initial} />;
}
