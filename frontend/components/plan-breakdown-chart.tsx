"use client";

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

export function PlanBreakdownChart({ data }: { data: PlanSubscriberCount[] }) {
  if (data.length === 0) {
    return null;
  }
  const chartData = data.map((entry) => ({
    name: entry.plan_name ?? "No plan",
    count: entry.count,
    unassigned: entry.plan_id === null,
  }));
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
        <Bar dataKey="count" radius={[4, 4, 0, 0]} maxBarSize={48}>
          {chartData.map((entry) => (
            <Cell key={entry.name} fill={entry.unassigned ? UNASSIGNED_FILL : ASSIGNED_FILL} />
          ))}
        </Bar>
      </BarChart>
    </div>
  );
}
