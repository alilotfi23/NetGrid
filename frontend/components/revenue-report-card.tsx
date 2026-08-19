import { loadPaymentsReport } from "@/lib/api";
import { RevenueReportView } from "./revenue-report-view";

/**
 * Revenue report card for the invoices page. A server component: fetches the
 * backend server-side (no CORS, token stays out of the browser) and renders
 * the presentational view with either data or an error state.
 */
export async function RevenueReportCard() {
  const result = await loadPaymentsReport();
  if (!result.ok) {
    return <RevenueReportView error={result.error} />;
  }
  return <RevenueReportView report={result.report} />;
}
