import { loadDashboardKpis } from "@/lib/api";
import { DashboardKpisClient } from "./dashboard-kpis-client";

/**
 * Dashboard KPI strip. A server component: fetches the four headline stats
 * from the backend (token stays out of the browser) and hands them to the
 * polling client as the initial render, so the first paint is instant and
 * the client then refreshes the numbers every 30s.
 */
export async function DashboardKpis() {
  const initial = await loadDashboardKpis();
  return <DashboardKpisClient initial={initial} />;
}
