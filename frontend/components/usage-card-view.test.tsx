import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { UsageReportData, UsageRow } from "@/lib/api";

import { UsageCardView } from "./usage-card-view";

function row(overrides: Partial<UsageRow> = {}): UsageRow {
  return {
    subscriber_id: 1,
    username: "demo-a1",
    full_name: "Demo One",
    plan_id: 1,
    plan_name: "Starter",
    quota_gb: 100,
    enforce_quota: false,
    overage_price_per_gb: "0.50",
    window_start: "2026-08-01T00:00:00Z",
    window_end: "2026-09-01T00:00:00Z",
    input_octets: 512345678,
    output_octets: 1209876543,
    total_octets: 1722222221,
    total_gb: 1.6,
    session_count: 1,
    pct_used: 1.6,
    ...overrides,
  };
}

function usage(items: UsageRow[]): UsageReportData {
  return {
    items,
    total: items.length,
    stats: {
      total_consumed_gb: items.reduce((sum, r) => sum + r.total_gb, 0),
      over_quota_count: items.filter((r) => r.pct_used != null && r.pct_used >= 100).length,
    },
  };
}

describe("UsageCardView", () => {
  it("renders per-subscriber usage vs quota with a progress bar", () => {
    render(<UsageCardView usage={usage([row()])} />);

    expect(screen.getByRole("heading", { name: "Data cap usage" })).toBeTruthy();
    expect(screen.getByText("demo-a1")).toBeTruthy();
    expect(screen.getByText("1.6 GB / 100 GB")).toBeTruthy();
    expect(screen.getByText("1.6%")).toBeTruthy();
    expect(screen.getByText("Starter · 1 session")).toBeTruthy();

    const bar = screen.getByRole("progressbar", { name: "demo-a1 quota used" });
    expect(bar.getAttribute("aria-valuenow")).toBe("2"); // min(pct, 100) rounded
  });

  it("clamps the bar width to 100% and flags the subscriber over quota", () => {
    render(
      <UsageCardView
        usage={usage([
          row({ username: "heavy", total_gb: 120, pct_used: 120, session_count: 3 }),
        ])}
      />,
    );

    const bar = screen.getByRole("progressbar", { name: "heavy quota used" });
    expect(bar.getAttribute("aria-valuenow")).toBe("100");
    // over-quota count in the header
    expect(screen.getByText("1 over quota")).toBeTruthy();
  });

  it("shows the consumed-GB rollup when nothing is over quota", () => {
    render(
      <UsageCardView
        usage={usage([row(), row({ subscriber_id: 2, username: "demo-a2", total_gb: 0.5, pct_used: 0.5 })])}
      />,
    );

    expect(screen.getByText("2.1 GB used")).toBeTruthy();
  });

  it("renders the total-usage header link", () => {
    render(<UsageCardView usage={usage([row()])} />);

    const link = within(screen.getByRole("heading", { name: "Data cap usage" })).getByRole("link");
    expect(link.getAttribute("href")).toBe("/subscribers");
  });

  it("links each subscriber to their detail page", () => {
    render(<UsageCardView usage={usage([row()])} />);

    const link = screen.getByRole("link", { name: "demo-a1" });
    expect(link.getAttribute("href")).toBe("/subscribers/1");
  });

  it("caps the list and notes additional subscribers", () => {
    const many = Array.from({ length: 10 }, (_, i) =>
      row({ subscriber_id: i + 1, username: `user-${i + 1}` }),
    );
    render(<UsageCardView usage={usage(many)} />);

    expect(screen.getByText("…and 2 more plan-assigned subscribers.")).toBeTruthy();
  });

  it("renders the empty state", () => {
    render(<UsageCardView usage={usage([])} />);

    expect(screen.getByText("No plan-assigned subscribers yet.")).toBeTruthy();
  });

  it("renders the error state instead of usage", () => {
    render(<UsageCardView error="Usage unavailable" />);

    expect(screen.getByRole("heading", { name: "Data cap usage unavailable" })).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });
});
