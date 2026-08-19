import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SubscriberStats } from "@/lib/api";
import { StatsCardView } from "./stats-card-view";

const STATS: SubscriberStats = {
  active: 2,
  suspended: 1,
  expired: 1,
  total: 4,
  by_plan: [
    { plan_id: 1, plan_name: "Starter", count: 2 },
    { plan_id: null, plan_name: null, count: 2 },
  ],
};

describe("StatsCardView", () => {
  it("renders the status counts", () => {
    render(<StatsCardView stats={STATS} />);

    expect(screen.getByText("Active")).toBeTruthy();
    expect(screen.getByText("Suspended")).toBeTruthy();
    expect(screen.getByText("Expired")).toBeTruthy();
    expect(screen.getByText("4 total")).toBeTruthy();
    // "2": Active tile + Starter row + unassigned row; "1": both remaining tiles
    expect(screen.getAllByText("2")).toHaveLength(3);
    expect(screen.getAllByText("1")).toHaveLength(2);
  });

  it("renders the per-plan breakdown with unassigned labeled No plan", () => {
    render(<StatsCardView stats={STATS} />);

    expect(screen.getByText("Starter")).toBeTruthy();
    expect(screen.getByText("No plan")).toBeTruthy();
  });

  it("shows an empty message when there are no plans", () => {
    render(<StatsCardView stats={{ ...STATS, total: 0, by_plan: [] }} />);

    expect(screen.getByText("No subscribers yet.")).toBeTruthy();
  });

  it("renders the error state when stats are unavailable", () => {
    render(<StatsCardView error="subscriber stats request failed: HTTP 403" />);

    expect(screen.getByText("Subscriber stats unavailable")).toBeTruthy();
    expect(screen.getByText("subscriber stats request failed: HTTP 403")).toBeTruthy();
  });
});
