import type { PaymentReportRow } from "./api";

export type RevenueTrendPoint = {
  /** "YYYY-MM" bucket, oldest first, ending in the current month. */
  month: string;
  /** Revenue for the month as a "X.XX" decimal string. */
  revenue: string;
};

/** The "YYYY-MM" labels for the trailing `count` months ending at `end`. */
function monthLabels(end: Date, count: number): string[] {
  const labels: string[] = [];
  const cursor = new Date(end.getFullYear(), end.getMonth(), 1);
  for (let i = 0; i < count; i += 1) {
    labels.unshift(
      `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, "0")}`,
    );
    cursor.setMonth(cursor.getMonth() - 1);
  }
  return labels;
}

/**
 * Build the trailing-12-month revenue series from the payments report rows,
 * which are grouped by (month, method) with months that had no payments
 * absent. Aggregates across payment methods, fills the gaps with zero so the
 * trend always spans a full 12 buckets, and returns oldest → newest ending
 * in the current month.
 *
 * Money is summed in cents (never floats) and emitted back as a "X.XX"
 * decimal string, matching how the backend serializes amounts.
 */
export function buildRevenueTrend(
  rows: PaymentReportRow[],
  now: Date = new Date(),
  months = 12,
): RevenueTrendPoint[] {
  const centsByMonth = new Map<string, number>();
  for (const row of rows) {
    const cents = Math.round(Number(row.revenue) * 100);
    if (!Number.isFinite(cents)) continue;
    centsByMonth.set(row.month, (centsByMonth.get(row.month) ?? 0) + cents);
  }

  return monthLabels(now, months).map((month) => ({
    month,
    revenue: ((centsByMonth.get(month) ?? 0) / 100).toFixed(2),
  }));
}
