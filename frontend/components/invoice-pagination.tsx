"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

export type PageNumber = number | "…";

/**
 * Page numbers with ellipsis for large ranges, e.g. current=5, total=12 ->
 * [1, "…", 4, 5, 6, "…", 12]. Near the edges the window flushes to the
 * bounds: current=1, total=12 -> [1, 2, 3, 4, 5, "…", 12].
 */
export function pageNumbers(current: number, total: number): PageNumber[] {
  if (total <= 7) return Array.from({ length: total }, (_, i) => i + 1);
  if (current <= 4) {
    return [...Array.from({ length: 5 }, (_, i) => i + 1), "…", total];
  }
  if (current >= total - 3) {
    return [1, "…", ...Array.from({ length: 5 }, (_, i) => total - 4 + i)];
  }
  return [1, "…", current - 1, current, current + 1, "…", total];
}

type Props = {
  page: number;
  pageSize: number;
  total: number;
  /** Preserve the invoice status filter when paging. */
  status?: string;
  /** Preserve the revenue report year filter when paging. */
  year?: string;
};

const PAGE_SIZES = [10, 20, 50, 100];

const linkClass =
  "rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 " +
  "transition-colors hover:bg-zinc-100 disabled:pointer-events-none disabled:opacity-40 " +
  "dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900";

/**
 * Pagination controls for the invoices table, backed by the API's page and
 * page_size params. Server-rendered links navigate pages; the page-size
 * select (a client control) resets to page 1. Both preserve the status and
 * year filters.
 */
export function InvoicePagination({ page, pageSize, total, status, year }: Props) {
  const router = useRouter();
  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  const current = Math.min(page, totalPages);
  const start = total === 0 ? 0 : (current - 1) * pageSize + 1;
  const end = Math.min(current * pageSize, total);

  function buildHref(nextPage: number, nextSize: number): string {
    const params = new URLSearchParams();
    params.set("page", String(nextPage));
    params.set("page_size", String(nextSize));
    if (status) params.set("status", status);
    if (year) params.set("year", year);
    return `/invoices?${params.toString()}`;
  }

  if (totalPages <= 1) return null;

  return (
    <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
      <p className="text-xs text-zinc-500 dark:text-zinc-400">
        Showing {start}–{end} of {total} invoices
      </p>

      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Invoice pages" className="flex flex-wrap items-center gap-1.5">
          <Link
            href={buildHref(current - 1, pageSize)}
            aria-disabled={current === 1}
            className={`${linkClass} ${current === 1 ? "pointer-events-none opacity-40" : ""}`}
            tabIndex={current === 1 ? -1 : undefined}
          >
            Previous
          </Link>
          {pageNumbers(current, totalPages).map((item, index) =>
            item === "…" ? (
              <span key={`gap-${index}`} className="px-1 text-sm text-zinc-400 dark:text-zinc-600">
                …
              </span>
            ) : item === current ? (
              <span
                key={item}
                aria-current="page"
                className="rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white"
              >
                {item}
              </span>
            ) : (
              <Link
                key={item}
                href={buildHref(item, pageSize)}
                className={linkClass}
              >
                {item}
              </Link>
            ),
          )}
          <Link
            href={buildHref(current + 1, pageSize)}
            aria-disabled={current === totalPages}
            className={`${linkClass} ${current === totalPages ? "pointer-events-none opacity-40" : ""}`}
            tabIndex={current === totalPages ? -1 : undefined}
          >
            Next
          </Link>
        </nav>

        <label className="ml-2 flex items-center gap-2">
          <span className="text-xs text-zinc-500 dark:text-zinc-400">Per page</span>
          <select
            aria-label="Invoices per page"
            value={pageSize}
            onChange={(e) => router.push(buildHref(1, Number(e.target.value)))}
            className="rounded-lg border border-zinc-300 bg-white px-2 py-1.5 text-xs font-medium text-zinc-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
      </div>
    </div>
  );
}
