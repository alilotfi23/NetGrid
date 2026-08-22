import Link from "next/link";

import type { UsageReportData, UsageRow } from "@/lib/api";
import { formatBytes } from "@/lib/format";

const MAX_ROWS = 8;

/** Bar color by utilization: green < 80%, amber 80–100%, red over quota. */
function barColor(pct: number | null): string {
  if (pct == null) return "bg-zinc-300 dark:bg-zinc-700";
  if (pct >= 100) return "bg-red-500";
  if (pct >= 80) return "bg-amber-500";
  return "bg-emerald-500";
}

function UsageRowBar({ row }: { row: UsageRow }) {
  const pct = row.pct_used;
  const width = pct == null ? 0 : Math.min(pct, 100);
  const quotaLabel = row.quota_gb != null ? `${row.quota_gb} GB` : "unlimited";

  return (
    <li className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
      <div className="flex items-baseline justify-between gap-3">
        <Link
          href={`/subscribers/${row.subscriber_id}`}
          className="truncate text-sm font-medium text-zinc-900 transition-colors hover:text-indigo-600 dark:text-zinc-50 dark:hover:text-indigo-400"
        >
          {row.username}
        </Link>
        <span className="shrink-0 text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
          {formatBytes(row.total_octets)} / {quotaLabel}
          {pct != null && (
            <span
              className={`ml-1.5 font-semibold ${
                pct >= 100
                  ? "text-red-600 dark:text-red-400"
                  : pct >= 80
                    ? "text-amber-600 dark:text-amber-400"
                    : "text-zinc-900 dark:text-zinc-50"
              }`}
            >
              {pct.toFixed(1)}%
            </span>
          )}
        </span>
      </div>
      <div
        role="progressbar"
        aria-valuenow={Math.round(width)}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={`${row.username} quota used`}
        className="mt-2 h-2 w-full rounded-full bg-zinc-100 dark:bg-zinc-800"
      >
        <div
          className={`h-2 rounded-full ${barColor(pct)}`}
          style={{ width: `${width}%` }}
        />
      </div>
      <p className="mt-1 truncate text-xs text-zinc-500 dark:text-zinc-400">
        {row.plan_name} · {row.session_count} session{row.session_count === 1 ? "" : "s"}
      </p>
    </li>
  );
}

export function UsageCardView({
  usage,
  error,
}: {
  usage?: UsageReportData;
  error?: string;
}) {
  if (error || !usage) {
    return (
      <section
        aria-label="Data cap usage"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Data cap usage unavailable
        </h2>
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Sign in to the dashboard to refresh the session.
        </p>
      </section>
    );
  }

  const shown = usage.items.slice(0, MAX_ROWS);
  const hidden = usage.items.length - shown.length;

  return (
    <section
      aria-label="Data cap usage"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          <Link
            href="/subscribers"
            className="transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            Data cap usage
          </Link>
        </h2>
        <Link
          href="/subscribers"
          className="text-xs text-zinc-500 transition-colors hover:text-indigo-600 hover:underline dark:text-zinc-400 dark:hover:text-indigo-400"
        >
          {usage.stats.over_quota_count > 0 ? (
            <span className="font-semibold text-red-600 dark:text-red-400">
              {usage.stats.over_quota_count} over quota
            </span>
          ) : (
            <span>{usage.stats.total_consumed_gb.toFixed(1)} GB used</span>
          )}
        </Link>
      </div>

      {usage.items.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No plan-assigned subscribers yet.
        </p>
      ) : (
        <>
          <ul className="mt-4 grid grid-cols-1 gap-3">
            {shown.map((row) => (
              <UsageRowBar key={row.subscriber_id} row={row} />
            ))}
          </ul>
          {hidden > 0 && (
            <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
              …and {hidden} more plan-assigned subscriber{hidden === 1 ? "" : "s"}.
            </p>
          )}
        </>
      )}
    </section>
  );
}
