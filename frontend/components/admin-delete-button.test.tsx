import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminDeleteButton } from "./admin-delete-button";

const { refreshMock } = vi.hoisted(() => ({
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: refreshMock }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  refreshMock.mockClear();
});

describe("AdminDeleteButton", () => {
  it("opens a confirmation dialog naming the admin", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<AdminDeleteButton adminId={3} adminUsername="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("Delete admin account?");
    expect(dialog.textContent).toContain("bob");
    expect(dialog.textContent).toContain("cannot be undone");
  });

  it("DELETEs through the BFF and refreshes on confirm", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) }),
    );
    render(<AdminDeleteButton adminId={3} adminUsername="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/admins/3");
    expect(init?.method).toBe("DELETE");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("surfaces the backend error and keeps the dialog open", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ error: "Cannot delete yourself" }),
      }),
    );
    render(<AdminDeleteButton adminId={3} adminUsername="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Cannot delete yourself");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
