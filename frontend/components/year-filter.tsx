"use client";

import { useRouter } from "next/navigation";

type Props = {
  /** The currently selected year ("YYYY") or null when showing all years. */
  currentYear: string | null;
  /** Preserve the invoice status filter when changing the year. */
  status?: string;
};

const RECENT_YEARS = 4; // current year + 3 back

const selectClass =
  "rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs font-medium " +
  "text-zinc-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300";

/**
 * Year filter for the payments revenue report. Navigates to /invoices?year=
 * (server-side filter), preserving the invoice status filter if one is set.
 */
export function YearFilter({ currentYear, status }: Props) {
  const router = useRouter();
  const thisYear = new Date().getFullYear();
  const years = Array.from({ length: RECENT_YEARS }, (_, i) => thisYear - i);

  function onChange(event: React.ChangeEvent<HTMLSelectElement>) {
    const params = new URLSearchParams();
    if (event.target.value) params.set("year", event.target.value);
    if (status) params.set("status", status);
    const qs = params.toString();
    router.push(`/invoices${qs ? `?${qs}` : ""}`);
  }

  return (
    <label className="flex items-center gap-2">
      <span className="text-xs text-zinc-500 dark:text-zinc-400">Year</span>
      <select
        aria-label="Filter revenue by year"
        value={currentYear ?? ""}
        onChange={onChange}
        className={selectClass}
      >
        <option value="">All years</option>
        {years.map((year) => (
          <option key={year} value={year}>
            {year}
          </option>
        ))}
      </select>
    </label>
  );
}
