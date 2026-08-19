import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { PlanSubscriberCount } from "@/lib/api";
import { PlanBreakdownChart } from "./plan-breakdown-chart";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

const DATA: PlanSubscriberCount[] = [
  { plan_id: 1, plan_name: "Starter", count: 2 },
  { plan_id: null, plan_name: null, count: 2 },
];

afterEach(() => {
  pushMock.mockClear();
});

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

  it("navigates to the plan-filtered list when a bar is clicked", () => {
    const { container } = render(<PlanBreakdownChart data={DATA} />);

    const bars = container.querySelectorAll(".recharts-bar-rectangle");
    fireEvent.click(bars[0]); // Starter -> plan_id filter
    expect(pushMock).toHaveBeenCalledWith("/subscribers?plan_id=1");

    fireEvent.click(bars[1]); // No plan -> no_plan filter
    expect(pushMock).toHaveBeenCalledWith("/subscribers?no_plan=1");
  });

  it("renders nothing for empty data", () => {
    const { container } = render(<PlanBreakdownChart data={[]} />);

    expect(container.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(0);
  });
});
