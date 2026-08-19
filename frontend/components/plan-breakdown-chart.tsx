"use client";

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

import type { PlanSubscriberCount } from "@/lib/api";

const CHART_WIDTH = 560;
const CHART_HEIGHT = 180;
const ASSIGNED_FILL = "#6366f1"; // indigo-500
const UNASSIGNED_FILL = "#a1a1aa"; // zinc-400
const AXIS_TICK_FILL = "#a1a1aa";
const GRID_STROKE = "#e4e4e7";

type ChartEntry = {
  name: string;
  count: number;
  unassigned: boolean;
  href: string;
};

export function PlanBreakdownChart({ data }: { data: PlanSubscriberCount[] }) {
  const router = useRouter();

  if (data.length === 0) {
    return null;
  }
  const chartData: ChartEntry[] = data.map((entry) => ({
    name: entry.plan_name ?? "No plan",
    count: entry.count,
    unassigned: entry.plan_id === null,
    href:
      entry.plan_id == null
        ? "/subscribers?no_plan=1"
        : `/subscribers?plan_id=${entry.plan_id}`,
  }));
  // recharts Bar onClick receives the clicked bar's props, which carry the
  // datum as `payload` — drill down to the plan-filtered subscriber list.
  function handleBarClick(bar: unknown) {
    const href = (bar as { payload?: { href?: string } } | undefined)?.payload?.href;
    if (href) {
      router.push(href);
    }
  }

  return (
    <div
      role="img"
      aria-label="Subscribers per plan"
      className="overflow-x-auto"
    >
      <BarChart
        width={CHART_WIDTH}
        height={CHART_HEIGHT}
        data={chartData}
        margin={{ top: 8, right: 8, bottom: 0, left: -12 }}
      >
        <CartesianGrid stroke={GRID_STROKE} strokeOpacity={0.5} vertical={false} />
        <XAxis
          dataKey="name"
          tick={{ fill: AXIS_TICK_FILL, fontSize: 12 }}
          tickLine={false}
          axisLine={{ stroke: GRID_STROKE }}
          interval={0}
        />
        <YAxis
          allowDecimals={false}
          domain={[0, "dataMax"]}
          width={32}
          tick={{ fill: AXIS_TICK_FILL, fontSize: 12 }}
          tickLine={false}
          axisLine={false}
        />
        <Tooltip
          cursor={{ fill: "rgba(99, 102, 241, 0.08)" }}
          contentStyle={{
            borderRadius: 8,
            border: "1px solid #e4e4e7",
            fontSize: 12,
          }}
        />
        <Bar
          dataKey="count"
          radius={[4, 4, 0, 0]}
          maxBarSize={48}
          cursor="pointer"
          onClick={handleBarClick}
        >
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={entry.unassigned ? UNASSIGNED_FILL : ASSIGNED_FILL} />
          ))}
        </Bar>
      </BarChart>
    </div>
  );
}
