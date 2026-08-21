import Link from "next/link";

import { formatCurrency } from "@/lib/format";

/**
 * The headline numbers for one dashboard tile. `null` means the caller
 * couldn't load that metric (e.g. the viewer lacks the resource's read
 * permission), and the tile renders an em dash instead of a wrong number.
 */
export type DashboardKpis = {
  activeSubscribers: number | null;
  liveSessions: number | null;
  revenueYearToDate: string | null;
  overdueCount: number | null;
  overdueAmount: string | null;
};

function Tile({
  href,
  label,
  value,
  valueClassName,
  hint,
}: {
  href: string;
  label: string;
  value: string;
  valueClassName: string;
  hint?: string;
}) {
  return (
    <Link
      href={href}
      className="rounded-xl border border-zinc-200 bg-white p-4 shadow-sm transition-colors hover:border-indigo-300 dark:border-zinc-800 dark:bg-zinc-950 dark:hover:border-indigo-700"
    >
      <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
      <dd className={`mt-1 text-2xl font-semibold tabular-nums ${valueClassName}`}>
        {value}
      </dd>
      {hint && <dd className="mt-0.5 text-xs text-zinc-400 dark:text-zinc-500">{hint}</dd>}
    </Link>
  );
}

/**
 * Presentational KPI strip for the dashboard: active subscribers, live
 * sessions, revenue this year, and overdue amount, each linking to its page.
 * Renders an error card only when every metric failed to load; individual
 * missing metrics render an em dash.
 */
export function DashboardKpisView({
  kpis,
  error,
}: {
  kpis?: DashboardKpis;
  error?: string;
}) {
  if (error || !kpis) {
    return (
      <section
        aria-label="Dashboard stats"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Dashboard stats unavailable
        </h2>
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Sign in to the dashboard to refresh the session.
        </p>
      </section>
    );
  }

  return (
    <dl
      aria-label="Dashboard stats"
      className="grid grid-cols-2 gap-3 lg:grid-cols-4"
    >
      <Tile
        href="/subscribers"
        label="Active subscribers"
        value={kpis.activeSubscribers != null ? String(kpis.activeSubscribers) : "—"}
        valueClassName="text-emerald-600 dark:text-emerald-400"
      />
      <Tile
        href="/sessions"
        label="Live sessions"
        value={kpis.liveSessions != null ? String(kpis.liveSessions) : "—"}
        valueClassName="text-indigo-600 dark:text-indigo-400"
      />
      <Tile
        href="/invoices"
        label="Revenue (YTD)"
        value={formatCurrency(kpis.revenueYearToDate)}
        valueClassName="text-zinc-900 dark:text-zinc-50"
      />
      <Tile
        href="/invoices?status=overdue"
        label="Overdue"
        value={formatCurrency(kpis.overdueAmount)}
        valueClassName="text-rose-600 dark:text-rose-400"
        hint={kpis.overdueCount != null ? `${kpis.overdueCount} invoices past due` : undefined}
      />
    </dl>
  );
}
