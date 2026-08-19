import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminStatusButton } from "./admin-status-button";

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

describe("AdminStatusButton", () => {
  it("PATCHes is_active through the BFF and refreshes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => ({ is_active: false }) }),
    );
    render(<AdminStatusButton adminId={3} isActive />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/admins/3");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ is_active: false });
  });

  it("shows Activate for inactive admins", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<AdminStatusButton adminId={3} isActive={false} />);

    expect(screen.getByRole("button", { name: "Activate" })).toBeTruthy();
  });

  it("surfaces the backend error inline", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 400,
        json: async () => ({ error: "Cannot deactivate yourself" }),
      }),
    );
    render(<AdminStatusButton adminId={3} isActive />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));

    expect((await screen.findByText("Cannot deactivate yourself"))).toBeTruthy();
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
