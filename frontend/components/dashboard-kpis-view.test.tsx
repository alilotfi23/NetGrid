import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { DashboardKpisView, type DashboardKpis } from "./dashboard-kpis-view";

const KPIS: DashboardKpis = {
  activeSubscribers: 42,
  liveSessions: 7,
  revenueYearToDate: "1234.50",
  overdueCount: 2,
  overdueAmount: "99.99",
};

describe("DashboardKpisView", () => {
  it("renders the four headline stats", () => {
    const { container } = render(<DashboardKpisView kpis={KPIS} />);

    const dl = container.querySelector("dl");
    expect(dl).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("Active subscribers")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("42")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("Live sessions")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("7")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("Revenue (YTD)")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("$1,234.50")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("Overdue")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("$99.99")).toBeTruthy();
  });

  it("links each tile to its page", () => {
    render(<DashboardKpisView kpis={KPIS} />);

    const tile = (label: string) =>
      screen.getByRole("link", { name: new RegExp(label) });
    expect(tile("Active subscribers").getAttribute("href")).toBe("/subscribers");
    expect(tile("Live sessions").getAttribute("href")).toBe("/sessions");
    expect(tile("Revenue").getAttribute("href")).toBe("/invoices");
    expect(tile("Overdue").getAttribute("href")).toBe("/invoices?status=overdue");
  });

  it("shows the overdue invoice count as a hint", () => {
    render(<DashboardKpisView kpis={KPIS} />);

    expect(screen.getByText("2 invoices past due")).toBeTruthy();
  });

  it("renders an em dash for metrics that could not be loaded", () => {
    render(
      <DashboardKpisView
        kpis={{
          activeSubscribers: null,
          liveSessions: null,
          revenueYearToDate: null,
          overdueCount: null,
          overdueAmount: null,
        }}
      />,
    );

    expect(screen.getAllByText("—")).toHaveLength(4);
    expect(screen.queryByText("2 invoices past due")).toBeNull();
  });

  it("renders the error state when nothing can be loaded", () => {
    render(<DashboardKpisView error="request failed: HTTP 403" />);

    expect(screen.getByText("Dashboard stats unavailable")).toBeTruthy();
    expect(screen.getByText("request failed: HTTP 403")).toBeTruthy();
  });
});
