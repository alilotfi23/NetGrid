import Link from "next/link";

import type { NasDeviceTypeCount } from "@/lib/api";

export function NasTypeBreakdownView({
  byType,
  error,
}: {
  byType?: NasDeviceTypeCount[];
  error?: string;
}) {
  if (error) {
    return (
      <section
        aria-label="NAS devices by type"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          NAS devices by type unavailable
        </h2>
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
      </section>
    );
  }

  const rows = byType ?? [];
  const max = Math.max(0, ...rows.map((row) => row.count));

  return (
    <section
      aria-label="NAS devices by type"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">By NAS type</h2>
      {rows.length === 0 ? (
        <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">No NAS devices yet.</p>
      ) : (
        <ul className="mt-3 space-y-3">
          {rows.map(({ nas_type, count }) => (
            <li key={nas_type} className="text-sm">
              <Link
                href={`/nas-devices?nas_type=${encodeURIComponent(nas_type)}`}
                className="-mx-1 block rounded-lg px-1 py-0.5 transition-colors hover:bg-zinc-100 dark:hover:bg-zinc-900"
              >
                <div className="flex items-baseline justify-between text-zinc-700 dark:text-zinc-300">
                  <span className="capitalize">{nas_type}</span>
                  <span className="tabular-nums text-zinc-500 dark:text-zinc-400">{count}</span>
                </div>
                <div className="mt-1 h-1.5 w-full rounded-full bg-zinc-100 dark:bg-zinc-900">
                  <div
                    className="h-1.5 rounded-full bg-indigo-500"
                    style={{ width: max > 0 ? `${(count / max) * 100}%` : "0%" }}
                  />
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
