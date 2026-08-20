import { loadInvoices } from "@/lib/api";
import { OverdueAlertView } from "./overdue-alert-view";

/**
 * Dashboard overdue alert. A server component: fetches the invoice stats
 * server-side (token stays out of the browser) filtered to overdue invoices.
 * Renders nothing when the caller can't read invoices (e.g. an auditor-less
 * role or expired session) or when there is nothing overdue, so the banner
 * only ever surfaces a real problem.
 */
export async function OverdueAlertCard() {
  const result = await loadInvoices({ status: "overdue", pageSize: 1 });
  if (!result.ok || result.total === 0) return null;
  // stats are global (not filtered by status), so stats.overdue_amount is the
  // outstanding overdue total across all invoices; result.total is the count.
  return <OverdueAlertView count={result.total} amount={result.stats.overdue_amount} />;
}
