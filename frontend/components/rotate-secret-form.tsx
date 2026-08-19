"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50";

const labelClass = "block text-xs font-medium text-zinc-500 dark:text-zinc-400";

/**
 * Dedicated secret rotation for a NAS device. Posts to the BFF rotate-secret
 * route, which calls FastAPI's POST /nas-devices/{id}/rotate-secret — the new
 * secret is re-encrypted at rest and the FreeRADIUS nas row is rewritten
 * without touching any other device field.
 */
export function RotateSecretForm({ deviceId, deviceName }: { deviceId: number; deviceName: string }) {
  const router = useRouter();
  const [secret, setSecret] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setSuccess(false);

    if (!secret.trim()) {
      setError("New shared secret is required");
      return;
    }
    if (secret.length > 63) {
      setError("Shared secret is limited to 63 characters (RFC 2865)");
      return;
    }
    if (secret !== confirm) {
      setError("Secrets do not match");
      return;
    }

    setSubmitting(true);
    try {
      const res = await fetch(`/api/nas-devices/${deviceId}/rotate-secret`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ secret }),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      setSecret("");
      setConfirm("");
      setSuccess(true);
      router.refresh();
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4">
      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
        >
          {error}
        </p>
      )}
      {success && (
        <p
          role="status"
          className="rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
        >
          Shared secret for {deviceName} rotated. FreeRADIUS will use the new
          secret on the next RADIUS request.
        </p>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="new_secret" className={labelClass}>
            New shared secret
          </label>
          <input
            id="new_secret"
            type="password"
            autoComplete="new-password"
            maxLength={63}
            className={inputClass}
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="confirm_secret" className={labelClass}>
            Confirm new secret
          </label>
          <input
            id="confirm_secret"
            type="password"
            autoComplete="new-password"
            maxLength={63}
            className={inputClass}
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-amber-500 disabled:opacity-50"
        >
          {submitting ? "Rotating…" : "Rotate secret"}
        </button>
      </div>
    </form>
  );
}
