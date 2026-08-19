import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SignOutButton } from "./sign-out-button";

const { pushMock, refreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  pushMock.mockClear();
  refreshMock.mockClear();
});

describe("SignOutButton", () => {
  it("POSTs to the logout route and navigates to /login", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));
    render(<SignOutButton />);

    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/login"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/auth/logout");
    expect(init?.method).toBe("POST");
  });
});
