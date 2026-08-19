"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type Props = {
  deviceId: number;
  deviceName: string;
};

/**
 * Destructive delete action for a NAS device, gated behind an inline
 * confirmation dialog. On confirm it DELETEs through the BFF route handler,
 * which removes the inventory row and the FreeRADIUS nas row in one
 * transaction, then refreshes the list.
 */
export function NasDeviceDeleteButton({ deviceId, deviceName }: Props) {
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

  async function confirmDelete() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/nas-devices/${deviceId}`, { method: "DELETE" });
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
        className="text-red-600 hover:underline dark:text-red-400"
      >
        Delete
      </button>

      {open && (
        <div
          role="dialog"
          aria-modal="true"
          aria-labelledby="nas-delete-title"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          onMouseDown={(e) => {
            // close when the backdrop itself is clicked
            if (e.target === e.currentTarget) setOpen(false);
          }}
        >
          <div className="w-full max-w-sm rounded-xl border border-zinc-200 bg-white p-5 shadow-lg dark:border-zinc-800 dark:bg-zinc-950">
            <h2 id="nas-delete-title" className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
              Delete NAS device?
            </h2>
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              This permanently removes{" "}
              <span className="font-medium text-zinc-900 dark:text-zinc-50">{deviceName}</span>{" "}
              and its FreeRADIUS nas row — FreeRADIUS will reject its RADIUS
              requests as unknown. This cannot be undone.
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
                onClick={confirmDelete}
                disabled={busy}
                className="rounded-lg bg-red-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-red-500 disabled:opacity-50"
              >
                {busy ? "Deleting…" : "Delete"}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
