import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { PaymentReport } from "@/lib/api";
import { RevenueReportView, methodLabel } from "./revenue-report-view";

const REPORT: PaymentReport = {
  items: [
    { month: "2026-03", method: "cash", revenue: "10.00", count: 1 },
    { month: "2026-02", method: "bank_transfer", revenue: "25.00", count: 2 },
  ],
  total_revenue: "35.00",
};

describe("methodLabel", () => {
  it("maps known methods to readable labels and passes others through", () => {
    expect(methodLabel("bank_transfer")).toBe("Bank transfer");
    expect(methodLabel("other")).toBe("Other");
    expect(methodLabel("unknown_method")).toBe("unknown_method");
  });
});

describe("RevenueReportView", () => {
  it("renders the revenue rows, month buckets, and the grand total", () => {
    render(<RevenueReportView report={REPORT} />);

    expect(screen.getByText("Mar 2026")).toBeTruthy();
    expect(screen.getByText("Feb 2026")).toBeTruthy();
    expect(screen.getByText("Cash")).toBeTruthy();
    expect(screen.getByText("Bank transfer")).toBeTruthy();
    expect(screen.getByText("$10.00")).toBeTruthy();
    expect(screen.getByText("$25.00")).toBeTruthy();
    expect(screen.getByText("Total revenue")).toBeTruthy();
    expect(screen.getByText("$35.00")).toBeTruthy();
  });

  it("shows a friendly empty state when there are no payments", () => {
    render(<RevenueReportView report={{ items: [], total_revenue: "0.00" }} />);

    expect(screen.getByText(/No completed payments yet/)).toBeTruthy();
  });

  it("shows the error state instead of a table", () => {
    render(<RevenueReportView error="request failed: HTTP 403" />);

    expect(screen.getByText("Revenue report unavailable")).toBeTruthy();
    expect(screen.getByText("request failed: HTTP 403")).toBeTruthy();
    expect(screen.queryByText("Total revenue")).toBeNull();
  });
});
