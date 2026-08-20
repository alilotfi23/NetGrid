import Link from "next/link";

import { formatCurrency } from "@/lib/format";

/**
 * Presentational overdue banner. Rendered only when there are overdue
 * invoices (the server card returns null otherwise), so no empty state is
 * needed here.
 */
export function OverdueAlertView({ count, amount }: { count: number; amount: string }) {
  return (
    <section
      aria-label="Overdue invoices alert"
      role="alert"
      className="mb-6 flex flex-wrap items-center gap-x-4 gap-y-3 rounded-xl border border-rose-200 bg-rose-50 px-5 py-4 dark:border-rose-900 dark:bg-rose-950/40"
    >
      <svg
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="size-6 shrink-0 text-rose-600 dark:text-rose-400"
        aria-hidden="true"
      >
        <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
        <path d="M12 9v4" />
        <path d="M12 17h.01" />
      </svg>
      <p className="min-w-0 flex-1 text-sm text-rose-900 dark:text-rose-200">
        <span className="font-semibold">
          {count} {count === 1 ? "invoice" : "invoices"} overdue
        </span>{" "}
        — {formatCurrency(amount)} outstanding and past due.
      </p>
      <Link
        href="/invoices?status=overdue"
        className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-rose-700"
      >
        View overdue invoices
      </Link>
    </section>
  );
}
