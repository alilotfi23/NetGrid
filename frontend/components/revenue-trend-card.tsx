import { loadPaymentsReport } from "@/lib/api";
import { buildRevenueTrend } from "@/lib/revenue-trend";
import { RevenueTrendView } from "./revenue-trend-view";

/**
 * Dashboard card for the trailing-12-month revenue trend. A server
 * component: fetches the full payments report server-side (token stays out
 * of the browser) and narrows it to the last 12 months, zero-filling months
 * without payments so the trend always spans a complete window.
 */
export async function RevenueTrendCard() {
  const result = await loadPaymentsReport();
  if (!result.ok) {
    return <RevenueTrendView error={result.error} />;
  }
  return <RevenueTrendView points={buildRevenueTrend(result.report.items)} />;
}
