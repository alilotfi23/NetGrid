import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { AuditLogEntry } from "@/lib/api";
import { RecentActivityView } from "./recent-activity-view";

function entry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 1,
    admin_id: 1,
    admin_username: "superadmin",
    action: "create",
    resource: "subscribers",
    resource_id: "12",
    metadata_: null,
    created_at: new Date(Date.now() - 5 * 60 * 1000).toISOString(),
    ...overrides,
  };
}

describe("RecentActivityView", () => {
  it("renders the actor, action, resource, and relative time per entry", () => {
    render(<RecentActivityView entries={[entry()]} />);

    expect(screen.getByText("create")).toBeTruthy();
    expect(screen.getByText(/subscribers/)).toBeTruthy();
    expect(screen.getByText("#12")).toBeTruthy();
    expect(screen.getByText(/superadmin/)).toBeTruthy();
    expect(screen.getByText(/5m ago/)).toBeTruthy();
  });

  it("links drillable resources to their detail pages", () => {
    render(<RecentActivityView entries={[entry()]} />);

    // \s* tolerates the whitespace collapse jsdom applies to accessible names
    const link = screen.getByRole("link", { name: /subscribers\s*#\s*12/ });
    expect(link.getAttribute("href")).toBe("/subscribers/12");
  });

  it("renders resources without a detail page as plain text", () => {
    render(
      <RecentActivityView
        entries={[
          entry({ resource: "auth", resource_id: null, action: "login" }),
          entry({ resource: "sessions", resource_id: "99", action: "disconnect" }),
        ]}
      />,
    );

    expect(screen.queryByRole("link", { name: /auth/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /sessions\s*#\s*99/ })).toBeNull();
    expect(screen.getByText(/sessions/)).toBeTruthy();
  });

  it("labels system actors and shows the empty state", () => {
    render(
      <RecentActivityView
        entries={[entry({ admin_id: null, admin_username: null, resource: "invoices" })]}
      />,
    );
    expect(screen.getByText(/system/)).toBeTruthy();

    render(<RecentActivityView entries={[]} />);
    expect(screen.getByText(/No recent activity yet/)).toBeTruthy();
  });

  it("links the heading and View all to the audit log page", () => {
    render(<RecentActivityView entries={[entry()]} />);

    const headingLink = screen.getByRole("link", { name: "Recent activity" });
    expect(headingLink.getAttribute("href")).toBe("/audit-logs");
    expect(screen.getByRole("link", { name: "View all" }).getAttribute("href")).toBe("/audit-logs");
  });
});
