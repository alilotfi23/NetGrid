import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Invoice } from "@/lib/api";
import { PaymentForm } from "./payment-form";

const { refreshMock } = vi.hoisted(() => ({
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: refreshMock }),
}));

const INVOICE: Invoice = {
  id: 12,
  subscriber_id: 7,
  subscriber_username: "bob",
  plan_name: "Starter",
  period_start: "2026-03-01",
  period_end: "2026-03-30",
  amount: "10.00",
  status: "issued",
  issued_at: "2026-03-01T00:00:00",
  due_at: "2026-03-30",
  paid_at: null,
  payments: [
    {
      id: 1,
      invoice_id: 12,
      amount: "4.00",
      method: "bank_transfer",
      reference: "TXN-1",
      status: "completed",
      created_at: "2026-03-05T00:00:00",
    },
  ],
};

function mockFetchOnce(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
  refreshMock.mockClear();
});

describe("PaymentForm", () => {
  it("prefills the amount with the remaining balance", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<PaymentForm invoice={INVOICE} />);

    expect(screen.getByLabelText("Amount")).toHaveProperty("value", "6.00");
    expect(screen.getByText("$10.00")).toBeTruthy();
    expect(screen.getByText("$6.00")).toBeTruthy();
  });

  it("POSTs the payment through the BFF and refreshes on success", async () => {
    mockFetchOnce({
      ok: true,
      status: 201,
      json: async () => ({
        payment: { id: 2, invoice_id: 12, amount: "6.00", method: "cash", status: "completed" },
        invoice: { ...INVOICE, status: "paid", payments: [] },
      }),
    });
    render(<PaymentForm invoice={INVOICE} />);

    fireEvent.change(screen.getByLabelText("Method"), { target: { value: "cash" } });
    fireEvent.change(screen.getByLabelText("Reference (optional)"), {
      target: { value: "TXN-9" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/invoices/12/payments");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      amount: "6.00",
      method: "cash",
      reference: "TXN-9",
    });
  });

  it("rejects amounts above the remaining balance", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<PaymentForm invoice={INVOICE} />);

    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "7.00" } });
    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));

    expect((await screen.findByRole("alert")).textContent).toContain("remaining");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("rejects non-positive amounts", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<PaymentForm invoice={INVOICE} />);

    fireEvent.change(screen.getByLabelText("Amount"), { target: { value: "0" } });
    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));

    expect((await screen.findByRole("alert")).textContent).toContain("greater than zero");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("surfaces the backend error and stays on the form", async () => {
    mockFetchOnce({
      ok: false,
      status: 409,
      json: async () => ({ error: "Invoice already paid" }),
    });
    render(<PaymentForm invoice={INVOICE} />);

    fireEvent.click(screen.getByRole("button", { name: "Record payment" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Invoice already paid");
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
