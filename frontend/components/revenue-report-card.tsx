import { loadPaymentsReport } from "@/lib/api";
import { RevenueReportView } from "./revenue-report-view";

/**
 * Revenue report card for the invoices page. A server component: fetches the
 * backend server-side (no CORS, token stays out of the browser) and renders
 * the presentational view with either data or an error state. `year` narrows
 * the report to one calendar year via the backend's ?year= parameter.
 */
export async function RevenueReportCard({
  year,
  status,
}: {
  year?: number;
  status?: string;
}) {
  const result = await loadPaymentsReport(year);
  if (!result.ok) {
    return <RevenueReportView error={result.error} />;
  }
  return (
    <RevenueReportView
      report={result.report}
      currentYear={year != null ? String(year) : null}
      status={status}
    />
  );
}
