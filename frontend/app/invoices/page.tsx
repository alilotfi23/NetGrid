import Link from "next/link";

import { GenerateInvoicesButton } from "@/components/generate-invoices-button";
import { InvoicePagination } from "@/components/invoice-pagination";
import { Nav } from "@/components/nav";
import { RevenueReportCard } from "@/components/revenue-report-card";
import { type Invoice, loadInvoices } from "@/lib/api";
import { formatCurrency, formatDay } from "@/lib/format";

// Live billing data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

const statusStyles: Record<string, string> = {
  issued: "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  paid: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  overdue: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
};

function statusBadge(status: string) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
        statusStyles[status] ?? "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
      }`}
    >
      {status}
    </span>
  );
}

const STATUS_FILTERS = [
  { value: "", label: "All" },
  { value: "issued", label: "Issued" },
  { value: "paid", label: "Paid" },
  { value: "overdue", label: "Overdue" },
];

/** Status-filter chip href, preserving the report's ?year= filter. */
function statusHref(status: string, year: string | undefined): string {
  const params = new URLSearchParams();
  if (status) params.set("status", status);
  if (year) params.set("year", year);
  const qs = params.toString();
  return qs ? `/invoices?${qs}` : "/invoices";
}

function InvoiceTable({ invoices }: { invoices: Invoice[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Invoice</th>
            <th className="px-4 py-3 font-medium">Subscriber</th>
            <th className="px-4 py-3 font-medium">Plan</th>
            <th className="px-4 py-3 font-medium">Period</th>
            <th className="px-4 py-3 font-medium">Amount</th>
            <th className="px-4 py-3 font-medium">Due</th>
            <th className="px-4 py-3 font-medium">Status</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {invoices.map((invoice) => (
            <tr key={invoice.id} className="text-zinc-700 dark:text-zinc-300">
              <td className="px-4 py-3">
                <Link
                  href={`/invoices/${invoice.id}`}
                  className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  #{invoice.id}
                </Link>
              </td>
              <td className="px-4 py-3">
                {invoice.subscriber_username == null ? (
                  <span className="text-zinc-400 dark:text-zinc-600">#{invoice.subscriber_id}</span>
                ) : (
                  <Link
                    href={`/subscribers/${invoice.subscriber_id}`}
                    className="text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    {invoice.subscriber_username}
                  </Link>
                )}
              </td>
              <td className="px-4 py-3">{invoice.plan_name}</td>
              <td className="px-4 py-3 whitespace-nowrap">
                {formatDay(invoice.period_start)} – {formatDay(invoice.period_end)}
              </td>
              <td className="px-4 py-3 tabular-nums">{formatCurrency(invoice.amount)}</td>
              <td className="px-4 py-3 whitespace-nowrap">{formatDay(invoice.due_at)}</td>
              <td className="px-4 py-3">{statusBadge(invoice.status)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

const DEFAULT_PAGE_SIZE = 20;

/** Parse a positive integer query param, falling back to a default. */
function intParam(value: string | undefined, fallback: number): number {
  if (value == null) return fallback;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : fallback;
}

export default async function InvoicesPage({
  searchParams,
}: {
  searchParams: Promise<{ status?: string; year?: string; page?: string; page_size?: string }>;
}) {
  const { status, year, page, page_size } = await searchParams;
  // only forward a valid calendar year (2000-2100, matching the backend's
  // query validation); anything else is treated as "all years"
  const parsedYear = year != null ? Number(year) : NaN;
  const reportYear = Number.isInteger(parsedYear) && parsedYear >= 2000 && parsedYear <= 2100
    ? parsedYear
    : undefined;
  // page_size is clamped to the backend's 1-100 range
  const pageSize = Math.min(100, intParam(page_size, DEFAULT_PAGE_SIZE));
  const pageNumber = intParam(page, 1);
  const result = await loadInvoices({ status, page: pageNumber, pageSize });

  const tiles = [
    { key: "issued", label: "Issued", className: "text-sky-600 dark:text-sky-400" },
    { key: "paid", label: "Paid", className: "text-emerald-600 dark:text-emerald-400" },
    { key: "overdue", label: "Overdue", className: "text-rose-600 dark:text-rose-400" },
  ] as const;

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Invoices
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Monthly bills for active subscribers. Payments accumulate against
              an invoice; it flips to paid once completed payments reach its
              amount.
            </p>
          </div>
          <GenerateInvoicesButton />
        </div>

        {!result.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Invoices unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{result.error}</p>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Sign in to the dashboard to refresh the session.
            </p>
          </div>
        ) : (
          <>
            <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
              {tiles.map(({ key, label, className }) => (
                <div
                  key={key}
                  className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
                >
                  <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
                  <dd className={`mt-1 text-2xl font-semibold tabular-nums ${className}`}>
                    {result.stats[key]}
                  </dd>
                </div>
              ))}
              <div className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
                <dt className="text-xs text-zinc-500 dark:text-zinc-400">Outstanding</dt>
                <dd className="mt-1 text-2xl font-semibold tabular-nums text-zinc-900 dark:text-zinc-50">
                  {formatCurrency(result.stats.outstanding_amount)}
                </dd>
              </div>
            </dl>

            <div className="mt-6">
              <RevenueReportCard year={reportYear} status={status} />
            </div>

            <div className="mt-6 flex items-center gap-2">
              {STATUS_FILTERS.map((filter) => {
                const active = status === filter.value;
                return (
                  <Link
                    key={filter.value}
                    href={statusHref(filter.value, reportYear != null ? String(reportYear) : undefined)}
                    className={
                      active
                        ? "rounded-full bg-indigo-600 px-3 py-1 text-xs font-medium text-white"
                        : "rounded-full border border-zinc-300 px-3 py-1 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
                    }
                  >
                    {filter.label}
                  </Link>
                );
              })}
            </div>

            {result.invoices.length === 0 ? (
              <p className="mt-4 rounded-xl border border-zinc-200 bg-white p-5 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
                {result.total > 0
                  ? "No invoices on this page."
                  : status
                    ? `No ${status} invoices.`
                    : "No invoices yet. Generate them for the current month."}
              </p>
            ) : (
              <div className="mt-4">
                <InvoiceTable invoices={result.invoices} />
              </div>
            )}
            <InvoicePagination
              page={result.page}
              pageSize={result.pageSize}
              total={result.total}
              status={status}
              year={reportYear != null ? String(reportYear) : undefined}
            />
          </>
        )}
      </div>
    </main>
  );
}
