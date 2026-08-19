import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { YearFilter } from "./year-filter";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(() => {
  pushMock.mockClear();
});

describe("YearFilter", () => {
  it("offers all years plus the recent four, showing the current year", () => {
    render(<YearFilter currentYear={null} />);

    expect(screen.getByLabelText("Filter revenue by year")).toHaveProperty("value", "");
    const thisYear = new Date().getFullYear();
    expect(screen.getByRole("option", { name: "All years" })).toBeTruthy();
    for (const year of [thisYear, thisYear - 1, thisYear - 2, thisYear - 3]) {
      expect(screen.getByRole("option", { name: String(year) })).toBeTruthy();
    }
  });

  it("shows the active year as the select value", () => {
    render(<YearFilter currentYear="2025" />);
    expect(screen.getByLabelText("Filter revenue by year")).toHaveProperty("value", "2025");
  });

  it("navigates to /invoices?year= on change", () => {
    render(<YearFilter currentYear={null} />);

    fireEvent.change(screen.getByLabelText("Filter revenue by year"), {
      target: { value: "2025" },
    });

    expect(pushMock).toHaveBeenCalledWith("/invoices?year=2025");
  });

  it("preserves the invoice status filter when changing the year", () => {
    render(<YearFilter currentYear={null} status="paid" />);

    fireEvent.change(screen.getByLabelText("Filter revenue by year"), {
      target: { value: "2024" },
    });

    expect(pushMock).toHaveBeenCalledWith("/invoices?year=2024&status=paid");
  });

  it("returns to all years when cleared", () => {
    render(<YearFilter currentYear="2025" status="issued" />);

    fireEvent.change(screen.getByLabelText("Filter revenue by year"), {
      target: { value: "" },
    });

    expect(pushMock).toHaveBeenCalledWith("/invoices?status=issued");
  });
});
