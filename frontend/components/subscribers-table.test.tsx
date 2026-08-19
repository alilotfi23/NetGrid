import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";

import type { Subscriber } from "@/lib/api";
import { SubscribersTable } from "./subscribers-table";

// next/link needs the router in RTL; render it as a plain anchor.
vi.mock("next/link", () => ({
  default: ({ href, children }: { href: string; children: ReactNode }) => (
    <a href={href}>{children}</a>
  ),
}));

const PLAN_NAMES: Record<number, string> = { 1: "Starter", 2: "Pro" };

function subscriber(overrides: Partial<Subscriber> & { id: number; username: string }): Subscriber {
  return {
    full_name: "Full Name",
    email: null,
    phone: null,
    status: "active",
    plan_id: null,
    notes: null,
    created_at: "2026-08-19T00:00:00",
    ...overrides,
  };
}

const SUBSCRIBERS: Subscriber[] = [
  subscriber({ id: 1, username: "alice", full_name: "Alice Admin", status: "active", plan_id: 1 }),
  subscriber({ id: 2, username: "bob", full_name: "Bob Billing", status: "suspended", plan_id: 2 }),
  subscriber({ id: 3, username: "carol", full_name: "Carol Care", status: "expired", plan_id: null }),
  subscriber({ id: 4, username: "dave", full_name: "Dave Dba", status: "active", plan_id: 1 }),
];

function bodyRows() {
  const table = screen.getByRole("table");
  return within(table).getAllByRole("row").slice(1); // drop the header row
}

describe("SubscribersTable", () => {
  it("renders every subscriber with status, plan, and a profile link", () => {
    render(<SubscribersTable subscribers={SUBSCRIBERS} planNames={PLAN_NAMES} />);

    expect(bodyRows()).toHaveLength(4);
    expect((screen.getByRole("link", { name: "alice" }) as HTMLAnchorElement).pathname).toBe(
      "/subscribers/1",
    );
    expect(screen.getByText("Alice Admin")).toBeTruthy();
    expect(screen.getByText("Bob Billing")).toBeTruthy();
    expect(screen.getByText("Carol Care")).toBeTruthy();
    // Status badges are capitalized by the cell renderer.
    expect(screen.getAllByText("active")).toHaveLength(2);
    expect(screen.getByText("suspended")).toBeTruthy();
    expect(screen.getByText("expired")).toBeTruthy();
    // Plan names resolve through the map; the unassigned row shows an em dash.
    expect(screen.getAllByText("Starter")).toHaveLength(2);
    expect(screen.getByText("Pro")).toBeTruthy();
    expect(screen.getByText("—")).toBeTruthy();
  });

  it("filters rows by search text and reports the visible count", () => {
    render(<SubscribersTable subscribers={SUBSCRIBERS} planNames={PLAN_NAMES} />);

    fireEvent.change(screen.getByRole("searchbox", { name: "Search subscribers" }), {
      target: { value: "carol" },
    });
    expect(bodyRows()).toHaveLength(1);
    expect(screen.getByText("Carol Care")).toBeTruthy();
    expect(screen.getByText("1 of 4 shown")).toBeTruthy();

    // Search matches across columns — plan names and statuses too.
    fireEvent.change(screen.getByRole("searchbox", { name: "Search subscribers" }), {
      target: { value: "Starter" },
    });
    expect(bodyRows()).toHaveLength(2);

    // Clearing the search restores every row.
    fireEvent.change(screen.getByRole("searchbox", { name: "Search subscribers" }), {
      target: { value: "" },
    });
    expect(bodyRows()).toHaveLength(4);
  });

  it("sorts rows when a column header is clicked", () => {
    render(<SubscribersTable subscribers={SUBSCRIBERS} planNames={PLAN_NAMES} />);

    const usernameHeader = screen.getByRole("columnheader", { name: /username/i });
    fireEvent.click(usernameHeader);
    // Ascending by username.
    expect(within(bodyRows()[0]).getByText("alice")).toBeTruthy();

    fireEvent.click(usernameHeader);
    // Descending by username.
    expect(within(bodyRows()[0]).getByText("dave")).toBeTruthy();
  });

  it("shows the empty state when there are no subscribers", () => {
    render(<SubscribersTable subscribers={[]} planNames={PLAN_NAMES} />);
    expect(screen.getByText("No subscribers yet.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });

  it("shows a no-match message when the search excludes every row", () => {
    render(<SubscribersTable subscribers={SUBSCRIBERS} planNames={PLAN_NAMES} />);
    fireEvent.change(screen.getByRole("searchbox", { name: "Search subscribers" }), {
      target: { value: "zzz-nonexistent" },
    });
    expect(screen.getByText("No subscribers match your search.")).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
  });
});
