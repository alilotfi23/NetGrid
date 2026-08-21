import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RevenueTrendPoint } from "@/lib/revenue-trend";
import { RevenueTrendView } from "./revenue-trend-view";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

// Trailing 12 months ending Aug 2026, oldest first.
const MONTHS = [
  "2025-09", "2025-10", "2025-11", "2025-12",
  "2026-01", "2026-02", "2026-03", "2026-04",
  "2026-05", "2026-06", "2026-07", "2026-08",
];

function points(...revenues: [string, string][]): RevenueTrendPoint[] {
  const map = new Map(revenues);
  return MONTHS.map((month) => ({ month, revenue: map.get(month) ?? "0.00" }));
}

const POINTS = points(["2026-04", "250.00"], ["2026-08", "1234.56"]);

// Every month non-zero: recharts only renders a bar element for months with
// revenue, so this is what makes all twelve bars present in the DOM.
const FULL_MONTHS = points(...MONTHS.map((month) => [month, "100.00"] as [string, string]));

afterEach(() => {
  pushMock.mockClear();
});

describe("RevenueTrendView", () => {
  it("renders the title and the 12-month total", () => {
    render(<RevenueTrendView points={POINTS} />);

    expect(screen.getByText("Revenue trend")).toBeTruthy();
    expect(screen.getByText("Total (12 mo):")).toBeTruthy();
    expect(screen.getByText("$1,484.56")).toBeTruthy();
  });

  it("renders one bar per month", () => {
    const { container } = render(<RevenueTrendView points={FULL_MONTHS} />);

    expect(screen.getByRole("img", { name: "Monthly revenue" })).toBeTruthy();
    expect(container.querySelectorAll(".recharts-bar-rectangle")).toHaveLength(12);
  });

  it("drills down to the year's revenue report when a bar is clicked", () => {
    const { container } = render(<RevenueTrendView points={FULL_MONTHS} />);

    const bars = container.querySelectorAll(".recharts-bar-rectangle");
    fireEvent.click(bars[11]); // Aug 2026 -> year 2026
    expect(pushMock).toHaveBeenCalledWith("/invoices?year=2026");

    fireEvent.click(bars[0]); // Sep 2025 -> year 2025
    expect(pushMock).toHaveBeenCalledWith("/invoices?year=2025");
  });

  it("links the heading to the invoices page", () => {
    render(<RevenueTrendView points={POINTS} />);

    const link = screen.getByRole("heading", { name: "Revenue trend" });
    expect(link.querySelector("a")?.getAttribute("href")).toBe("/invoices");
  });

  it("shows an empty message when the window has no revenue", () => {
    render(<RevenueTrendView points={points()} />);

    expect(screen.getByText(/No revenue in the last 12 months/)).toBeTruthy();
  });

  it("renders the error state when the report could not be loaded", () => {
    render(<RevenueTrendView error="request failed: HTTP 403" />);

    expect(screen.getByText("Revenue trend unavailable")).toBeTruthy();
    expect(screen.getByText("request failed: HTTP 403")).toBeTruthy();
  });
});
