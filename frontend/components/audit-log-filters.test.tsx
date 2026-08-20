import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuditLogFilters } from "@/lib/api";
import { AuditLogFilters as AuditLogFiltersControl } from "./audit-log-filters";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(() => {
  pushMock.mockClear();
});

const FILTERS: AuditLogFilters = {
  actions: ["create", "login", "login_failed"],
  resources: ["auth", "plans", "rbac"],
  admins: [
    { id: 2, username: "superadmin" },
    { id: 3, username: "support" },
  ],
};

describe("AuditLogFilters", () => {
  it("renders the three selects populated from the filter options", () => {
    render(<AuditLogFiltersControl filters={FILTERS} />);

    expect(screen.getByLabelText("Filter by actor")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Filter by action")).toHaveProperty("value", "");
    expect(screen.getByLabelText("Filter by resource")).toHaveProperty("value", "");

    expect(screen.getByRole("option", { name: "All actors" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "superadmin" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "support" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "create" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "auth" })).toBeTruthy();
  });

  it("shows the active filters as the select values", () => {
    render(
      <AuditLogFiltersControl filters={FILTERS} adminId="2" action="login" resource="auth" />,
    );
    expect(screen.getByLabelText("Filter by actor")).toHaveProperty("value", "2");
    expect(screen.getByLabelText("Filter by action")).toHaveProperty("value", "login");
    expect(screen.getByLabelText("Filter by resource")).toHaveProperty("value", "auth");
  });

  it("navigates with the chosen actor, preserving the other filters", () => {
    render(<AuditLogFiltersControl filters={FILTERS} action="login" resource="auth" />);

    fireEvent.change(screen.getByLabelText("Filter by actor"), {
      target: { value: "2" },
    });

    expect(pushMock).toHaveBeenCalledWith("/audit-logs?admin_id=2&action=login&resource=auth");
  });

  it("navigates with only the changed action when no other filter is active", () => {
    render(<AuditLogFiltersControl filters={FILTERS} />);

    fireEvent.change(screen.getByLabelText("Filter by action"), {
      target: { value: "create" },
    });

    expect(pushMock).toHaveBeenCalledWith("/audit-logs?action=create");
  });

  it("clears a filter by navigating without it", () => {
    render(<AuditLogFiltersControl filters={FILTERS} adminId="2" action="login" />);

    fireEvent.change(screen.getByLabelText("Filter by action"), {
      target: { value: "" },
    });

    expect(pushMock).toHaveBeenCalledWith("/audit-logs?admin_id=2");
  });

  it("shows a reset link only when a filter is active", () => {
    const { rerender } = render(<AuditLogFiltersControl filters={FILTERS} />);
    expect(screen.queryByRole("link", { name: "Reset filters" })).toBeNull();

    rerender(<AuditLogFiltersControl filters={FILTERS} resource="rbac" />);
    const reset = screen.getByRole("link", { name: "Reset filters" });
    expect(reset.getAttribute("href")).toBe("/audit-logs");
  });
});
