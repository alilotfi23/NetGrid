import { describe, expect, it } from "vitest";

import type { PaymentReportRow } from "./api";
import { buildRevenueTrend } from "./revenue-trend";

// Fixed clock so the series is deterministic: Aug 2026 -> Sep 2025 .. Aug 2026.
const NOW = new Date(2026, 7, 15);

function row(month: string, method: string, revenue: string): PaymentReportRow {
  return { month, method, revenue, count: 1 };
}

describe("buildRevenueTrend", () => {
  it("returns twelve buckets ending in the current month, oldest first", () => {
    const points = buildRevenueTrend([], NOW);

    expect(points).toHaveLength(12);
    expect(points[0].month).toBe("2025-09");
    expect(points[11].month).toBe("2026-08");
  });

  it("aggregates revenue across payment methods within a month", () => {
    const points = buildRevenueTrend(
      [
        row("2026-07", "cash", "50.00"),
        row("2026-07", "card", "25.50"),
        row("2026-08", "cash", "10.25"),
      ],
      NOW,
    );

    const july = points.find((p) => p.month === "2026-07");
    const august = points.find((p) => p.month === "2026-08");
    expect(july?.revenue).toBe("75.50");
    expect(august?.revenue).toBe("10.25");
  });

  it("zero-fills months with no payments", () => {
    const points = buildRevenueTrend([row("2026-01", "cash", "99.99")], NOW);

    expect(points).toHaveLength(12);
    const january = points.find((p) => p.month === "2026-01");
    const february = points.find((p) => p.month === "2026-02");
    expect(january?.revenue).toBe("99.99");
    expect(february?.revenue).toBe("0.00");
    expect(points.filter((p) => p.revenue === "0.00")).toHaveLength(11);
  });

  it("ignores rows it cannot parse instead of corrupting the series", () => {
    const points = buildRevenueTrend(
      [row("2026-03", "cash", "not-a-number"), row("2026-03", "card", "5.00")],
      NOW,
    );

    const march = points.find((p) => p.month === "2026-03");
    expect(march?.revenue).toBe("5.00");
  });

  it("produces a zero series when there are no payments at all", () => {
    const points = buildRevenueTrend([], NOW);

    expect(points.every((p) => p.revenue === "0.00")).toBe(true);
  });
});
