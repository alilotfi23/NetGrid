import { loadPaymentsReport } from "@/lib/api";
import { buildRevenueTrend } from "@/lib/revenue-trend";
import { RevenueTrendCardClient } from "./revenue-trend-card-client";

/**
 * Dashboard card for the trailing-12-month revenue trend. A server
 * component: fetches the full payments report server-side (token stays out
 * of the browser), narrows it to the last 12 months (zero-filling months
 * without payments), and hands the points to the polling client as the
 * initial render — instant first paint, then a 30s refresh.
 */
export async function RevenueTrendCard() {
  const result = await loadPaymentsReport();
  if (!result.ok) {
    return <RevenueTrendCardClient initial={{ ok: false, error: result.error }} />;
  }
  return (
    <RevenueTrendCardClient
      initial={{ ok: true, points: buildRevenueTrend(result.report.items) }}
    />
  );
}
