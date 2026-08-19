import { render, screen, within } from "@testing-library/react";
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
  by_plan_status: [
    { plan_id: 1, plan_name: "Starter", status: "active", count: 2 },
    { plan_id: null, plan_name: null, status: "expired", count: 1 },
    { plan_id: null, plan_name: null, status: "suspended", count: 1 },
  ],
};

describe("StatsCardView", () => {
  it("renders the status counts", () => {
    const { container } = render(<StatsCardView stats={STATS} />);
    // scope to the status tiles so the chart's axis labels can't interfere
    const dl = container.querySelector("dl");
    expect(dl).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("Active")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("Suspended")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("Expired")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("4")).toBeTruthy();
    expect(within(dl as HTMLElement).getAllByText("2")).toHaveLength(1);
    expect(within(dl as HTMLElement).getAllByText("1")).toHaveLength(2);
    expect(screen.getByText("4 total")).toBeTruthy();
  });

  it("renders the per-plan breakdown as a chart", () => {
    render(<StatsCardView stats={STATS} />);

    expect(screen.getByRole("img", { name: "Subscribers per plan" })).toBeTruthy();
    expect(screen.getByText("Starter")).toBeTruthy();
    expect(screen.getByText("No plan")).toBeTruthy();
  });

  it("links the heading to the subscribers list", () => {
    render(<StatsCardView stats={STATS} />);

    const link = within(screen.getByRole("heading", { name: "Subscribers" })).getByRole("link");
    expect(link.getAttribute("href")).toBe("/subscribers");
  });

  it("links the total-summary line to the subscribers list", () => {
    render(<StatsCardView stats={STATS} />);

    const link = screen.getByRole("link", { name: "4 total" });
    expect(link.getAttribute("href")).toBe("/subscribers");
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
