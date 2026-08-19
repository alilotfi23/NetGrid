import Link from "next/link";

import type { NasDeviceStats } from "@/lib/api";

const TILES = [
  { key: "total", label: "Total", className: "text-zinc-900 dark:text-zinc-50" },
  { key: "active", label: "Active", className: "text-emerald-600 dark:text-emerald-400" },
  { key: "inactive", label: "Inactive", className: "text-zinc-500 dark:text-zinc-400" },
] as const;

export function NasStatsCardView({
  stats,
  error,
}: {
  stats?: NasDeviceStats;
  error?: string;
}) {
  if (error || !stats) {
    return (
      <section
        aria-label="NAS device stats"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          NAS devices unavailable
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
      aria-label="NAS device stats"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          <Link
            href="/nas-devices"
            className="transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            NAS Devices
          </Link>
        </h2>
        <Link
          href="/nas-devices"
          className="text-xs text-zinc-500 transition-colors hover:text-indigo-600 hover:underline dark:text-zinc-400 dark:hover:text-indigo-400"
        >
          {stats.active} of {stats.total} active
        </Link>
      </div>

      <dl className="mt-4 grid grid-cols-3 gap-3">
        {TILES.map(({ key, label, className }) => (
          <div key={key} className="rounded-lg border border-zinc-200 p-3 dark:border-zinc-800">
            <dt className="text-xs text-zinc-500 dark:text-zinc-400">{label}</dt>
            <dd className={`mt-1 text-2xl font-semibold tabular-nums ${className}`}>
              {stats[key]}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
