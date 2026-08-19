"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

type Props = {
  deviceId: number;
  isActive: boolean;
};

/**
 * Deactivate/activate toggle on the NAS devices list. PATCHes is_active through
 * the BFF route handler, which mirrors the change to the FreeRADIUS nas table
 * (deactivating removes the nas row, so FreeRADIUS rejects that NAS).
 */
export function NasDeviceStatusButton({ deviceId, isActive }: Props) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function toggle() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/nas-devices/${deviceId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ is_active: !isActive }),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      router.refresh();
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="inline-flex items-center gap-2">
      <button
        type="button"
        onClick={toggle}
        disabled={busy}
        className={
          isActive
            ? "rounded-md border border-zinc-300 px-2 py-1 text-xs font-medium text-zinc-600 transition-colors hover:bg-zinc-100 disabled:opacity-50 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
            : "rounded-md border border-emerald-300 px-2 py-1 text-xs font-medium text-emerald-700 transition-colors hover:bg-emerald-50 disabled:opacity-50 dark:border-emerald-800 dark:text-emerald-400 dark:hover:bg-emerald-950"
        }
      >
        {busy ? "…" : isActive ? "Deactivate" : "Activate"}
      </button>
      {error && <span className="text-xs text-red-600 dark:text-red-400">{error}</span>}
    </span>
  );
}
