import {
  loadInvoices,
  loadPaymentsReport,
  loadSessions,
  loadSubscriberStats,
} from "@/lib/api";
import { DashboardKpisView, type DashboardKpis } from "./dashboard-kpis-view";

/**
 * Dashboard KPI strip. A server component: fetches the four headline stats
 * from the backend in parallel (token stays out of the browser) and renders
 * the presentational view. Each metric loads independently — a viewer who
 * lacks one resource's read permission sees an em dash for that tile instead
 * of the whole strip failing.
 */
export async function DashboardKpis() {
  const [subscribers, sessions, report, overdue] = await Promise.all([
    loadSubscriberStats(),
    loadSessions(),
    loadPaymentsReport(new Date().getFullYear()),
    loadInvoices({ status: "overdue", pageSize: 1 }),
  ]);

  const errors = [
    subscribers.ok ? null : subscribers.error,
    sessions.ok ? null : sessions.error,
    report.ok ? null : report.error,
    overdue.ok ? null : overdue.error,
  ];
  const firstError = errors.find((err): err is string => Boolean(err));

  if (!subscribers.ok && !sessions.ok && !report.ok && !overdue.ok) {
    return <DashboardKpisView error={firstError ?? "Dashboard stats unavailable"} />;
  }

  const kpis: DashboardKpis = {
    activeSubscribers: subscribers.ok ? subscribers.stats.active : null,
    liveSessions: sessions.ok ? sessions.stats.total : null,
    revenueYearToDate: report.ok ? report.report.total_revenue : null,
    overdueCount: overdue.ok ? overdue.total : null,
    overdueAmount: overdue.ok ? overdue.stats.overdue_amount : null,
  };

  return <DashboardKpisView kpis={kpis} />;
}
