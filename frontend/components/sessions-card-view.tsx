import Link from "next/link";

import type { SessionStats } from "@/lib/api";

export function SessionsCardView({
  stats,
  error,
}: {
  stats?: SessionStats;
  error?: string;
}) {
  if (error || !stats) {
    return (
      <section
        aria-label="Live sessions"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Live sessions unavailable
        </h2>
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Sign in to the dashboard to refresh the session.
        </p>
      </section>
    );
  }

  const max = Math.max(0, ...stats.by_nas.map((row) => row.count));

  return (
    <section
      aria-label="Live sessions"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          <Link
            href="/sessions"
            className="transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            Live Sessions
          </Link>
        </h2>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          {stats.total} active
        </span>
      </div>

      {stats.by_nas.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No active sessions right now.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {stats.by_nas.map(({ nasipaddress, nas_shortname, count }) => (
            <li key={nasipaddress} className="text-sm">
              <div className="flex items-baseline justify-between text-zinc-700 dark:text-zinc-300">
                <span className={nas_shortname ? "font-medium" : "tabular-nums"}>
                  {nas_shortname ?? nasipaddress}
                </span>
                <span className="tabular-nums text-zinc-500 dark:text-zinc-400">{count}</span>
              </div>
              {nas_shortname && (
                <div className="mt-0.5 text-xs tabular-nums text-zinc-400 dark:text-zinc-500">
                  {nasipaddress}
                </div>
              )}
              <div className="mt-1 h-1.5 w-full rounded-full bg-zinc-100 dark:bg-zinc-900">
                <div
                  className="h-1.5 rounded-full bg-indigo-500"
                  style={{ width: max > 0 ? `${(count / max) * 100}%` : "0%" }}
                />
              </div>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
