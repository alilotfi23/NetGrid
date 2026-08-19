"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Props = {
  sessionId: number;
  username: string;
};

/**
 * Disconnect action for a live session, gated behind an inline confirmation
 * dialog. On confirm it POSTs through the BFF route handler, which sends an
 * RFC 5176 Disconnect-Request to the session's NAS, then refreshes the list.
 */
export function SessionDisconnectButton({ sessionId, username }: Props) {
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // close on Escape once open
  useEffect(() => {
    if (!open) return;
    function onKey(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  async function confirmDisconnect() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/sessions/${sessionId}/disconnect`, { method: "POST" });
      if (!res.ok) {
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      setOpen(false);
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-amber-600 hover:underline dark:text-amber-400"
      >
        Disconnect
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="session-disconnect-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onMouseDown={(e) => {
            // close when the backdrop itself is clicked
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
            <h2
              id="session-disconnect-title"
              className="text-base font-semibold text-zinc-900 dark:text-zinc-50"
            >
              Disconnect session?
            </h2>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              Sends an RFC 5176 Disconnect-Request to the NAS for{" "}
              <span className="font-medium text-zinc-900 dark:text-zinc-50">{username}</span>.
              The session is terminated immediately; the row closes once the NAS
              sends its Accounting-Stop.
            </p>

            {error && (
              <p
                role="alert"
                className="mt-3 rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
              >
                {error}
              </p>
            )}

            <div className="mt-5 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setOpen(false)}
                disabled={busy}
                className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={confirmDisconnect}
                disabled={busy}
                className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-500 disabled:opacity-50"
              >
                {busy ? "Disconnecting…" : "Disconnect"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
