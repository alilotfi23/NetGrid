import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GenerateInvoicesButton } from "./generate-invoices-button";

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

describe("GenerateInvoicesButton", () => {
  it("opens a confirmation dialog explaining idempotency", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<GenerateInvoicesButton />);

    fireEvent.click(screen.getByRole("button", { name: "Generate invoices" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("Generate invoices?");
    expect(dialog.textContent).toContain("safe to re-run");
  });

  it("POSTs through the BFF, shows the created count, and refreshes", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 200, json: async () => ({ created: 3 }) }),
    );
    render(<GenerateInvoicesButton />);

    fireEvent.click(screen.getByRole("button", { name: "Generate invoices" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Generate" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    expect((await screen.findByRole("status")).textContent).toContain("Created 3 invoices");
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/invoices/generate");
    expect(init?.method).toBe("POST");
  });

  it("surfaces the backend error and keeps the dialog open", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: async () => ({ error: "database connection lost" }),
      }),
    );
    render(<GenerateInvoicesButton />);

    fireEvent.click(screen.getByRole("button", { name: "Generate invoices" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Generate" }));

    expect((await screen.findByRole("alert")).textContent).toContain("database connection lost");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
