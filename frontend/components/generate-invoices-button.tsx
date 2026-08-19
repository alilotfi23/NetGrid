"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

/**
 * Manual trigger for the monthly invoice job. POSTs through the BFF route
 * handler (which calls POST /api/v1/invoices/generate) behind a confirmation
 * dialog; the run is idempotent, so re-running never double-bills.
 */
export function GenerateInvoicesButton() {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [created, setCreated] = useState<number | null>(null);

  // close on Escape once open
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function confirmGenerate() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/invoices/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const body = (await res.json().catch(() => null)) as
        | { error?: string; created?: number }
        | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      setCreated(body?.created ?? 0);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => {
          setCreated(null);
          setError(null);
          setOpen(true);
        }}
        className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
      >
        Generate invoices
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="generate-invoices-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onMouseDown={(e) => {
            // close when the backdrop itself is clicked
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
            <h2
              id="generate-invoices-title"
              className="text-base font-semibold text-zinc-900 dark:text-zinc-50"
            >
              Generate invoices?
            </h2>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              Bills every active subscriber on an active plan for the current
              calendar month. Subscribers already invoiced for an overlapping
              period are skipped, so this is safe to re-run.
            </p>

            {error && (
              <p
                role="alert"
                className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
              >
                {error}
              </p>
            )}
            {created != null && (
              <p
                role="status"
                className="mt-3 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
              >
                Created {created} invoice{created === 1 ? "" : "s"}.
              </p>
            )}

            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                disabled={busy}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
              >
                Close
              </button>
              <button
                type="button"
                onClick={confirmGenerate}
                disabled={busy || created != null}
                className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
              >
                {busy ? "Generating…" : "Generate"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
