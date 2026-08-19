"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import type { NasDevice } from "@/lib/api";

type NasDeviceFormValues = {
  name: string;
  ip_address: string;
  shortname: string;
  nas_type: string;
  secret: string;
  ports: string;
  server: string;
  community: string;
  description: string;
  is_active: boolean;
};

function initialValues(device?: NasDevice): NasDeviceFormValues {
  return {
    name: device?.name ?? "",
    ip_address: device?.ip_address ?? "",
    shortname: device?.shortname ?? "",
    nas_type: device?.nas_type ?? "other",
    // The secret is write-only: never prefilled, optional on edit (rotation).
    secret: "",
    ports: device?.ports != null ? String(device.ports) : "",
    server: device?.server ?? "",
    community: device?.community ?? "",
    description: device?.description ?? "",
    is_active: device?.is_active ?? true,
  };
}

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50";

const labelClass = "block text-xs font-medium text-zinc-500 dark:text-zinc-400";

const NAS_TYPES = [
  "other",
  "cisco",
  "mikrotik",
  "aruba",
  "ruckus_wireless",
  "juniper",
  "hp",
  "ubiquiti",
];

export function NasDeviceForm({ device }: { device?: NasDevice }) {
  const mode = device ? "edit" : "create";
  const router = useRouter();
  const [values, setValues] = useState<NasDeviceFormValues>(() => initialValues(device));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof NasDeviceFormValues>(key: K, value: NasDeviceFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!values.name.trim() || !values.shortname.trim()) {
      setError("Name and shortname are required");
      return;
    }
    if (!values.ip_address.trim() && mode === "create") {
      setError("IP address is required");
      return;
    }
    if (mode === "create" && !values.secret.trim()) {
      setError("Shared secret is required");
      return;
    }
    if (values.secret.length > 63) {
      setError("Shared secret is limited to 63 characters (RFC 2865)");
      return;
    }
    const ports = values.ports.trim() === "" ? null : Number(values.ports);
    if (ports !== null && (Number.isNaN(ports) || ports < 1 || ports > 65535)) {
      setError("Ports must be between 1 and 65535");
      return;
    }
    if (!values.nas_type.trim()) {
      setError("NAS type is required");
      return;
    }

    const payload: Record<string, unknown> = {
      name: values.name.trim(),
      shortname: values.shortname.trim(),
      nas_type: values.nas_type.trim(),
      ports,
      server: values.server.trim() === "" ? null : values.server.trim(),
      community: values.community.trim() === "" ? null : values.community.trim(),
      description: values.description.trim() === "" ? null : values.description.trim(),
      is_active: values.is_active,
    };
    if (mode === "create") {
      payload.ip_address = values.ip_address.trim();
      payload.secret = values.secret;
    } else if (values.secret.trim() !== "") {
      // Rotation only — blank means keep the current secret.
      payload.secret = values.secret;
    }

    setSubmitting(true);
    try {
      const res = await fetch(device ? `/api/nas-devices/${device.id}` : "/api/nas-devices", {
        method: device ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      router.push("/nas-devices");
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

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="name" className={labelClass}>
            Name
          </label>
          <input
            id="name"
            className={inputClass}
            value={values.name}
            onChange={(e) => set("name", e.target.value)}
          />
        </div>
        {mode === "create" ? (
          <div>
            <label htmlFor="ip_address" className={labelClass}>
              IP address
            </label>
            <input
              id="ip_address"
              className={inputClass}
              value={values.ip_address}
              onChange={(e) => set("ip_address", e.target.value)}
            />
            <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
              The RADIUS identity — immutable after creation.
            </p>
          </div>
        ) : (
          <div>
            <label htmlFor="ip_address" className={labelClass}>
              IP address
            </label>
            <input
              id="ip_address"
              className={inputClass}
              value={device?.ip_address ?? ""}
              disabled
              readOnly
            />
          </div>
        )}
        <div>
          <label htmlFor="shortname" className={labelClass}>
            Shortname
          </label>
          <input
            id="shortname"
            className={inputClass}
            value={values.shortname}
            onChange={(e) => set("shortname", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="nas_type" className={labelClass}>
            NAS type
          </label>
          <input
            id="nas_type"
            list="nas-types"
            className={inputClass}
            value={values.nas_type}
            onChange={(e) => set("nas_type", e.target.value)}
          />
          <datalist id="nas-types">
            {NAS_TYPES.map((t) => (
              <option key={t} value={t} />
            ))}
          </datalist>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label htmlFor="secret" className={labelClass}>
            {mode === "create" ? "Shared secret" : "New shared secret (optional)"}
          </label>
          <input
            id="secret"
            type="password"
            autoComplete="new-password"
            maxLength={63}
            className={inputClass}
            value={values.secret}
            onChange={(e) => set("secret", e.target.value)}
          />
          <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">
            {mode === "create"
              ? "Never shown again — stored encrypted."
              : "Leave blank to keep the current secret."}
          </p>
        </div>
        <div>
          <label htmlFor="ports" className={labelClass}>
            Ports (optional)
          </label>
          <input
            id="ports"
            type="number"
            min={1}
            max={65535}
            className={inputClass}
            value={values.ports}
            onChange={(e) => set("ports", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="server" className={labelClass}>
            Server (optional)
          </label>
          <input
            id="server"
            className={inputClass}
            value={values.server}
            onChange={(e) => set("server", e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="community" className={labelClass}>
            Community (optional)
          </label>
          <input
            id="community"
            className={inputClass}
            value={values.community}
            onChange={(e) => set("community", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="description" className={labelClass}>
            Description (optional)
          </label>
          <input
            id="description"
            className={inputClass}
            value={values.description}
            onChange={(e) => set("description", e.target.value)}
          />
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
        <input
          type="checkbox"
          checked={values.is_active}
          onChange={(e) => set("is_active", e.target.checked)}
        />
        Active — mirrored to the FreeRADIUS nas table
      </label>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Saving…" : mode === "create" ? "Create NAS device" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/nas-devices")}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
