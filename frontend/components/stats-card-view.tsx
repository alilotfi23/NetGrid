import Link from "next/link";

import type { SubscriberStats } from "@/lib/api";
import { PlanBreakdownChart } from "./plan-breakdown-chart";

const STATUS_TILES = [
  { key: "active", label: "Active", className: "text-emerald-600 dark:text-emerald-400" },
  { key: "suspended", label: "Suspended", className: "text-amber-600 dark:text-amber-400" },
  { key: "expired", label: "Expired", className: "text-red-600 dark:text-red-400" },
  { key: "total", label: "Total", className: "text-zinc-900 dark:text-zinc-50" },
] as const;

export function StatsCardView({
  stats,
  error,
}: {
  stats?: SubscriberStats;
  error?: string;
}) {
  if (error || !stats) {
    return (
      <section
        aria-label="Subscriber stats"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Subscriber stats unavailable
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
      aria-label="Subscriber stats"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          <Link
            href="/subscribers"
            className="transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            Subscribers
          </Link>
        </h2>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {stats.total} total
        </span>
      </div>

      <dl className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
        {STATUS_TILES.map(({ key, label, className }) => (
          <div
            key={key}
            className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800"
          >
            <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
            <dd className={`mt-1 text-2xl font-semibold tabular-nums ${className}`}>
              {stats[key]}
            </dd>
          </div>
        ))}
      </dl>

      <h3 className="mt-5 text-xs font-medium text-zinc-500 dark:text-zinc-400">
        By plan
      </h3>
      {stats.by_plan.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No subscribers yet.</p>
      ) : (
        <PlanBreakdownChart data={stats.by_plan} />
      )}
    </section>
  );
}
