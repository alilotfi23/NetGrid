"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import type { Invoice } from "@/lib/api";
import { formatCurrency } from "@/lib/format";

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50";

const labelClass = "block text-xs font-medium text-zinc-500 dark:text-zinc-400";

const METHODS = [
  { value: "cash", label: "Cash" },
  { value: "card", label: "Card" },
  { value: "bank_transfer", label: "Bank transfer" },
  { value: "wallet", label: "Wallet" },
  { value: "other", label: "Other" },
];

/**
 * Record a completed payment against an invoice (which flips it to paid once
 * completed payments reach its amount). POSTs through the BFF route handler,
 * then refreshes the detail page to show the updated payments list.
 */
export function PaymentForm({ invoice }: { invoice: Invoice }) {
  const router = useRouter();
  const paidTotal = invoice.payments.reduce((sum, p) => sum + Number(p.amount), 0);
  const remaining = Math.max(0, Number(invoice.amount) - paidTotal);

  const [amount, setAmount] = useState(remaining > 0 ? remaining.toFixed(2) : "");
  const [method, setMethod] = useState("cash");
  const [reference, setReference] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const value = Number(amount);
    if (!amount.trim() || Number.isNaN(value) || value <= 0) {
      setError("Amount must be greater than zero");
      return;
    }
    if (value > remaining + 0.001) {
      setError(`Amount can't exceed the remaining ${formatCurrency(remaining)}`);
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`/api/invoices/${invoice.id}/payments`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          amount: amount.trim(),
          method,
          reference: reference.trim() === "" ? null : reference.trim(),
        }),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      router.refresh();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Invoice total is <span className="font-medium text-zinc-900 dark:text-zinc-50">{formatCurrency(invoice.amount)}</span>;{" "}
        <span className="font-medium text-zinc-900 dark:text-zinc-50">{formatCurrency(remaining)}</span>{" "}
        remains unpaid.
      </p>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
        >
          {error}
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="payment-amount" className={labelClass}>
            Amount
          </label>
          <input
            id="payment-amount"
            className={inputClass}
            inputMode="decimal"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="payment-method" className={labelClass}>
            Method
          </label>
          <select
            id="payment-method"
            className={inputClass}
            value={method}
            onChange={(e) => setMethod(e.target.value)}
          >
            {METHODS.map((m) => (
              <option key={m.value} value={m.value}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div>
        <label htmlFor="payment-reference" className={labelClass}>
          Reference (optional)
        </label>
        <input
          id="payment-reference"
          className={inputClass}
          value={reference}
          onChange={(e) => setReference(e.target.value)}
        />
      </div>

      <button
        type="submit"
        disabled={submitting}
        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
      >
        {submitting ? "Recording…" : "Record payment"}
      </button>
    </form>
  );
}
