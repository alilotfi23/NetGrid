import type { SubscriberStats } from "@/lib/api";

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
          Set NETGRID_DEMO_TOKEN (an admin access token) for the server-side fetch.
        </p>
      </section>
    );
  }

  const maxPlanCount = Math.max(1, ...stats.by_plan.map((p) => p.count));

  return (
    <section
      aria-label="Subscriber stats"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">Subscribers</h2>
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
        <ul className="mt-2 space-y-2">
          {stats.by_plan.map((entry) => (
            <li key={entry.plan_id ?? "unassigned"} className="flex items-center gap-3">
              <span className="w-32 truncate text-sm text-zinc-700 dark:text-zinc-300">
                {entry.plan_name ?? "No plan"}
              </span>
              <div className="h-2 flex-1 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  className="h-full rounded-full bg-indigo-500"
                  style={{ width: `${(entry.count / maxPlanCount) * 100}%` }}
                />
              </div>
              <span className="w-8 text-right text-sm font-medium tabular-nums text-zinc-900 dark:text-zinc-50">
                {entry.count}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
