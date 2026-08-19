import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SessionDisconnectButton } from "./session-disconnect-button";

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

describe("SessionDisconnectButton", () => {
  it("opens a confirmation dialog naming the subscriber", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SessionDisconnectButton sessionId={3} username="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("Disconnect session?");
    expect(dialog.textContent).toContain("bob");
    expect(dialog.textContent).toContain("Disconnect-Request");
  });

  it("cancelling closes the dialog without fetching", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SessionDisconnectButton sessionId={3} username="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("POSTs through the BFF and refreshes on confirm", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({}) }),
    );
    render(<SessionDisconnectButton sessionId={3} username="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Disconnect" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/sessions/3/disconnect");
    expect(init?.method).toBe("POST");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("surfaces the backend error and keeps the dialog open", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ error: "NAS refused the disconnect request (Disconnect-NAK)" }),
      }),
    );
    render(<SessionDisconnectButton sessionId={3} username="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Disconnect" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Disconnect-NAK");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SessionDisconnectButton sessionId={3} username="bob" />);

    fireEvent.click(screen.getByRole("button", { name: "Disconnect" }));
    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
