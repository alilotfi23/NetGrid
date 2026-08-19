"use client";

import {
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createSortedRowModel,
  globalFilteringFeature,
  rowSortingFeature,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { SortDirection, SortingState } from "@tanstack/table-core";

import type { Subscriber } from "@/lib/api";

// Feature set is static — TanStack v9 registers features once, per table
// flavor, outside render. Global filtering builds on column filtering, so
// both features are registered (the row-model slots come after their
// prerequisite features).
const features = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  rowSortingFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
});

const helper = createColumnHelper<typeof features, Subscriber>();

const statusStyles: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  suspended: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  expired: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
};

function buildColumns(planNames: Record<number, string>) {
  // Single helper.columns(...) call so each nested column keeps its TValue
  // (spreading separately-declared defs collapses them to `unknown`).
  return helper.columns([
    helper.accessor("username", {
      header: "Username",
      cell: ({ row }) => (
        <Link
          href={`/subscribers/${row.original.id}`}
          className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
        >
          {row.original.username}
        </Link>
      ),
    }),
    helper.accessor("full_name", { header: "Full name" }),
    helper.accessor("status", {
      header: "Status",
      cell: ({ getValue }) => {
        const status = getValue();
        return (
          <span
            className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
              statusStyles[status] ?? "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
            }`}
          >
            {status}
          </span>
        );
      },
    }),
    helper.accessor(
      (s) => (s.plan_id != null ? (planNames[s.plan_id] ?? `Plan #${s.plan_id}`) : ""),
      {
        id: "plan",
        header: "Plan",
        cell: ({ getValue }) => {
          const name = getValue();
          return name === "" ? (
            <span className="text-zinc-400 dark:text-zinc-600">—</span>
          ) : (
            name
          );
        },
      },
    ),
  ]);
}

function sortIndicator(direction: false | SortDirection) {
  if (direction === "asc") return <span className="ml-1 text-indigo-500">↑</span>;
  if (direction === "desc") return <span className="ml-1 text-indigo-500">↓</span>;
  return null;
}

export function SubscribersTable({
  subscribers,
  planNames,
}: {
  subscribers: Subscriber[];
  planNames: Record<number, string>;
}) {
  const [sorting, setSorting] = useState<SortingState>([]);
  const [globalFilter, setGlobalFilter] = useState("");

  // Column defs are rebuilt only when the plan-name map changes; stable
  // identities keep TanStack's per-column state (sorting, etc.) intact.
  const columns = useMemo(() => buildColumns(planNames), [planNames]);

  const table = useTable({
    features,
    columns,
    data: subscribers,
    state: { sorting, globalFilter },
    onSortingChange: setSorting,
    onGlobalFilterChange: setGlobalFilter,
  });

  const rows = table.getRowModel().rows;
  const filtered = globalFilter.trim() !== "";

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-3">
        <input
          type="search"
          aria-label="Search subscribers"
          placeholder="Search by username, name, status, or plan…"
          value={globalFilter}
          onChange={(e) => setGlobalFilter(e.target.value)}
          className="w-full max-w-xs rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50"
        />
        {filtered && (
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {rows.length} of {subscribers.length} shown
          </p>
        )}
      </div>

      {subscribers.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">No subscribers yet.</p>
      ) : rows.length === 0 ? (
        <p className="text-sm text-zinc-500 dark:text-zinc-400">
          No subscribers match your search.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
              <tr>
                {table.getHeaderGroups()[0].headers.map((header) => (
                  <th
                    key={header.id}
                    className="cursor-pointer select-none px-4 py-3 font-medium hover:text-zinc-900 dark:hover:text-zinc-100"
                    onClick={() => header.column.toggleSorting()}
                  >
                    {header.isPlaceholder ? null : (
                      <span className="inline-flex items-center">
                        <table.FlexRender header={header} />
                        {sortIndicator(header.column.getIsSorted())}
                      </span>
                    )}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {rows.map((row) => (
                <tr
                  key={row.id}
                  className="bg-white hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900"
                >
                  {row.getAllCells().map((cell) => (
                    <td key={cell.id} className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                      <table.FlexRender cell={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
