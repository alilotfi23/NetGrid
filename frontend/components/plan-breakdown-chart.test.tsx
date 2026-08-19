import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PlanSubscriberCount } from "@/lib/api";
import { PlanBreakdownChart } from "./plan-breakdown-chart";

const DATA: PlanSubscriberCount[] = [
  { plan_id: 1, plan_name: "Starter", count: 2 },
  { plan_id: null, plan_name: null, count: 2 },
];

describe("PlanBreakdownChart", () => {
  it("renders one bar per plan entry", () => {
    const { container } = render(<PlanBreakdownChart data={DATA} />);

    expect(screen.getByRole("img", { name: "Subscribers per plan" })).toBeTruthy();
    expect(container.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(2);
  });

  it("labels the unassigned bucket as No plan on the axis", () => {
    render(<PlanBreakdownChart data={DATA} />);

    expect(screen.getByText("Starter")).toBeTruthy();
    expect(screen.getByText("No plan")).toBeTruthy();
  });

  it("renders nothing for empty data", () => {
    const { container } = render(<PlanBreakdownChart data={[]} />);

    expect(container.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(0);
  });
});
