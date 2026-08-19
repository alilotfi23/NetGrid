import type { PaymentReport } from "@/lib/api";
import { formatCurrency, formatMonth } from "@/lib/format";
import { YearFilter } from "./year-filter";

const METHOD_LABELS: Record<string, string> = {
  cash: "Cash",
  card: "Card",
  bank_transfer: "Bank transfer",
  wallet: "Wallet",
  other: "Other",
};

export function methodLabel(method: string): string {
  return METHOD_LABELS[method] ?? method;
}

/**
 * Presentational card for the payments revenue report: completed-payment
 * revenue grouped by (month, method), newest month first, with the grand
 * total. `currentYear`/`status` drive the year filter, which navigates to
 * /invoices?year= (server-side filtering against the backend).
 */
export function RevenueReportView({
  report,
  error,
  currentYear,
  status,
}: {
  report?: PaymentReport;
  error?: string;
  currentYear?: string | null;
  status?: string;
}) {
  if (error || !report) {
    return (
      <section
        aria-label="Revenue report"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Revenue report unavailable
        </h2>
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Sign in to the dashboard to refresh the session.
        </p>
      </section>
    );
  }

  return (
    <section
      aria-label="Revenue report"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex items-baseline justify-between gap-3">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Payments revenue
        </h2>
        <div className="flex items-baseline gap-3">
          <span className="text-xs text-zinc-500 dark:text-zinc-400">
            {report.items.reduce((sum, row) => sum + row.count, 0)} payments
          </span>
          <YearFilter currentYear={currentYear ?? null} status={status} />
        </div>
      </div>

      {report.items.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No completed payments yet. Revenue appears here once payments are
          recorded against invoices.
        </p>
      ) : (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
              <tr>
                <th className="px-3 py-2 font-medium">Month</th>
                <th className="px-3 py-2 font-medium">Method</th>
                <th className="px-3 py-2 text-right font-medium">Payments</th>
                <th className="px-3 py-2 text-right font-medium">Revenue</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
              {report.items.map((row) => (
                <tr
                  key={`${row.month}-${row.method}`}
                  className="text-zinc-700 dark:text-zinc-300"
                >
                  <td className="px-3 py-2 whitespace-nowrap">
                    {formatMonth(row.month)}
                  </td>
                  <td className="px-3 py-2">{methodLabel(row.method)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {row.count}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatCurrency(row.revenue)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-zinc-200 font-medium text-zinc-900 dark:border-zinc-800 dark:text-zinc-50">
                <td className="px-3 py-2" colSpan={3}>
                  Total revenue
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatCurrency(report.total_revenue)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}
