"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { formatCurrency, formatMonth } from "@/lib/format";
import type { RevenueTrendPoint } from "@/lib/revenue-trend";

const CHART_WIDTH = 640;
const CHART_HEIGHT = 200;
const FILL = "#6366f1"; // indigo-500
const AXIS_TICK_FILL = "#a1a1aa";
const GRID_STROKE = "#e4e4e7";

/** Compact axis tick: $1.2k instead of $1,234.56. */
function compactCurrency(value: number): string {
  if (value >= 1000) {
    const thousands = value / 1000;
    const rounded = value % 1000 === 0 ? String(thousands) : thousands.toFixed(1);
    return `$${rounded}k`;
  }
  return `$${Math.round(value)}`;
}

/** "2026-08" -> "Aug" for the x-axis. */
function shortMonth(month: string): string {
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return month;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, 1);
  return date.toLocaleString("en-US", { month: "short" });
}

/**
 * Presentational card for the 12-month revenue trend. A bar per month,
 * oldest first, with a compact currency axis and a tooltip showing the full
 * amount; clicking a bar drills down to that year's revenue report on the
 * invoices page. Renders an empty message when the window has no revenue at
 * all and an error card when the data couldn't be loaded.
 */
export function RevenueTrendView({
  points,
  error,
}: {
  points?: RevenueTrendPoint[];
  error?: string;
}) {
  const router = useRouter();

  if (error || !points) {
    return (
      <section
        aria-label="Revenue trend"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          Revenue trend unavailable
        </h2>
        <p className="mt-2 text-sm text-red-600 dark:text-red-400">{error}</p>
        <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
          Sign in to the dashboard to refresh the session.
        </p>
      </section>
    );
  }

  const total = points.reduce((sum, point) => sum + Number(point.revenue), 0);

  if (total === 0) {
    return (
      <section
        aria-label="Revenue trend"
        className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
      >
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          <Link
            href="/invoices"
            className="transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            Revenue trend
          </Link>
        </h2>
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No revenue in the last 12 months yet. Payments appear here once
          they are recorded against invoices.
        </p>
      </section>
    );
  }

  const chartData = points.map((point) => ({
    month: point.month,
    revenue: Number(point.revenue),
  }));

  // recharts Bar onClick receives the clicked bar's props; drill down to the
  // year-filtered revenue report on the invoices page.
  function handleBarClick(bar: unknown) {
    const month = (bar as { payload?: { month?: string } } | undefined)?.payload?.month;
    if (month) {
      router.push(`/invoices?year=${month.slice(0, 4)}`);
    }
  }

  return (
    <section
      aria-label="Revenue trend"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          <Link
            href="/invoices"
            className="transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            Revenue trend
          </Link>
        </h2>
        <span className="text-xs text-zinc-500 dark:text-zinc-400">
          Total (12 mo): <span className="font-medium text-zinc-900 dark:text-zinc-50">{formatCurrency(total)}</span>
        </span>
      </div>

      <div role="img" aria-label="Monthly revenue" className="mt-4 overflow-x-auto">
        <BarChart
          width={CHART_WIDTH}
          height={CHART_HEIGHT}
          data={chartData}
          margin={{ top: 8, right: 8, bottom: 0, left: -8 }}
        >
          <CartesianGrid stroke={GRID_STROKE} strokeOpacity={0.5} vertical={false} />
          <XAxis
            dataKey="month"
            tickFormatter={shortMonth}
            tick={{ fill: AXIS_TICK_FILL, fontSize: 12 }}
            tickLine={false}
            axisLine={{ stroke: GRID_STROKE }}
            interval={0}
          />
          <YAxis
            tickFormatter={compactCurrency}
            allowDecimals={false}
            domain={[0, "dataMax"]}
            width={44}
            tick={{ fill: AXIS_TICK_FILL, fontSize: 12 }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            cursor={{ fill: "rgba(99, 102, 241, 0.08)" }}
            formatter={(value) => formatCurrency(Number(value))}
            labelFormatter={(label) => formatMonth(String(label))}
            contentStyle={{
              borderRadius: 8,
              border: "1px solid #e4e4e7",
              fontSize: 12,
            }}
          />
          <Bar
            dataKey="revenue"
            radius={[4, 4, 0, 0]}
            maxBarSize={40}
            cursor="pointer"
            onClick={handleBarClick}
          >
            {chartData.map((entry) => (
              <Cell key={entry.month} fill={FILL} />
            ))}
          </Bar>
        </BarChart>
      </div>
    </section>
  );
}
