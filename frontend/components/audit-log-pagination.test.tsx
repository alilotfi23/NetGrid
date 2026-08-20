import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AuditLogPagination, pageNumbers } from "./audit-log-pagination";

const { pushMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock }),
}));

afterEach(() => {
  pushMock.mockClear();
});

describe("pageNumbers", () => {
  it("lists every page for small ranges", () => {
    expect(pageNumbers(1, 5)).toEqual([1, 2, 3, 4, 5]);
  });

  it("uses ellipses around the current page for large ranges", () => {
    expect(pageNumbers(5, 12)).toEqual([1, "…", 4, 5, 6, "…", 12]);
    expect(pageNumbers(1, 12)).toEqual([1, 2, 3, 4, 5, "…", 12]);
    expect(pageNumbers(12, 12)).toEqual([1, "…", 8, 9, 10, 11, 12]);
  });
});

describe("AuditLogPagination", () => {
  it("renders nothing when everything fits on one page", () => {
    const { container } = render(<AuditLogPagination page={1} pageSize={20} total={8} />);
    expect(container.firstChild).toBeNull();
  });

  it("shows the visible range and page numbers", () => {
    render(<AuditLogPagination page={2} pageSize={20} total={42} />);

    expect(screen.getByText("Showing 21–40 of 42 entries")).toBeTruthy();
    expect(screen.getByRole("navigation", { name: "Audit log pages" })).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("2").getAttribute("aria-current")).toBe("page");
  });

  it("disables Previous on the first page", () => {
    render(<AuditLogPagination page={1} pageSize={20} total={60} />);

    const previous = screen.getByRole("link", { name: "Previous" });
    expect(previous.getAttribute("aria-disabled")).toBe("true");
    expect(previous.className).toContain("pointer-events-none");
  });

  it("disables Next on the last page", () => {
    render(<AuditLogPagination page={3} pageSize={20} total={60} />);

    const next = screen.getByRole("link", { name: "Next" });
    expect(next.getAttribute("aria-disabled")).toBe("true");
    expect(next.className).toContain("pointer-events-none");
  });

  it("builds page links that preserve the actor, action, and resource filters", () => {
    render(
      <AuditLogPagination
        page={1}
        pageSize={20}
        total={60}
        adminId="2"
        action="create"
        resource="plans"
      />,
    );

    const pageTwo = screen.getByRole("link", { name: "2" });
    expect(pageTwo.getAttribute("href")).toBe(
      "/audit-logs?page=2&page_size=20&admin_id=2&action=create&resource=plans",
    );
  });

  it("clamps an out-of-range page to the last page", () => {
    render(<AuditLogPagination page={99} pageSize={20} total={42} />);

    expect(screen.getByText("3").getAttribute("aria-current")).toBe("page");
    expect(screen.getByText("Showing 41–42 of 42 entries")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Next" }).getAttribute("aria-disabled")).toBe("true");
  });

  it("navigates to page 1 when the page size changes, preserving filters", () => {
    render(<AuditLogPagination page={3} pageSize={20} total={120} resource="auth" />);

    fireEvent.change(screen.getByLabelText("Entries per page"), {
      target: { value: "50" },
    });

    expect(pushMock).toHaveBeenCalledWith("/audit-logs?page=1&page_size=50&resource=auth");
  });
});
