import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { OverdueAlertView } from "./overdue-alert-view";

describe("OverdueAlertView", () => {
  it("renders the overdue count, outstanding amount, and CTA link", () => {
    render(<OverdueAlertView count={3} amount="30.00" />);

    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("3 invoices overdue");
    expect(alert.textContent).toContain("$30.00");
    expect(alert.textContent).toContain("outstanding and past due");

    const link = screen.getByRole("link", { name: "View overdue invoices" });
    expect(link.getAttribute("href")).toBe("/invoices?status=overdue");
  });

  it("uses the singular form for a single overdue invoice", () => {
    render(<OverdueAlertView count={1} amount="9.99" />);
    expect(screen.getByRole("alert").textContent).toContain("1 invoice overdue");
  });
});
