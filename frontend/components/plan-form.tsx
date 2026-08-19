"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import type { Plan } from "@/lib/api";

type PlanFormValues = {
  name: string;
  radius_group: string;
  price: string;
  duration_days: string;
  bandwidth_down_mbps: string;
  bandwidth_up_mbps: string;
  quota_gb: string;
  description: string;
  is_active: boolean;
};

function initialValues(plan?: Plan): PlanFormValues {
  return {
    name: plan?.name ?? "",
    radius_group: plan?.radius_group ?? "",
    price: plan?.price ?? "",
    duration_days: plan ? String(plan.duration_days) : "30",
    bandwidth_down_mbps: plan ? String(plan.bandwidth_down_mbps) : "10",
    bandwidth_up_mbps: plan ? String(plan.bandwidth_up_mbps) : "5",
    quota_gb: plan?.quota_gb != null ? String(plan.quota_gb) : "",
    description: plan?.description ?? "",
    is_active: plan?.is_active ?? true,
  };
}

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50";

const labelClass = "block text-xs font-medium text-zinc-500 dark:text-zinc-400";

export function PlanForm({ plan }: { plan?: Plan }) {
  const mode = plan ? "edit" : "create";
  const router = useRouter();
  const [values, setValues] = useState<PlanFormValues>(() => initialValues(plan));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof PlanFormValues>(key: K, value: PlanFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    const duration = Number(values.duration_days);
    const down = Number(values.bandwidth_down_mbps);
    const up = Number(values.bandwidth_up_mbps);
    const quota = values.quota_gb.trim() === "" ? null : Number(values.quota_gb);
    if (!values.name.trim() && mode === "create") {
      setError("Name is required");
      return;
    }
    if (mode === "create" && !values.radius_group.trim()) {
      setError("RADIUS group is required");
      return;
    }
    if (!values.price.trim() || Number.isNaN(Number(values.price))) {
      setError("Price must be a number");
      return;
    }
    if (Number.isNaN(duration) || duration < 1) {
      setError("Duration must be at least 1 day");
      return;
    }
    if (Number.isNaN(down) || down < 0 || Number.isNaN(up) || up < 0) {
      setError("Bandwidth must be zero or greater");
      return;
    }
    if (quota !== null && (Number.isNaN(quota) || quota < 0)) {
      setError("Quota must be zero or greater");
      return;
    }

    const payload = {
      name: values.name.trim(),
      radius_group: values.radius_group.trim(),
      price: values.price.trim(),
      duration_days: duration,
      bandwidth_down_mbps: down,
      bandwidth_up_mbps: up,
      quota_gb: quota,
      description: values.description.trim() === "" ? null : values.description.trim(),
      is_active: values.is_active,
    };

    setSubmitting(true);
    try {
      const res = await fetch(plan ? `/api/plans/${plan.id}` : "/api/plans", {
        method: plan ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      router.push("/plans");
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

      {mode === "create" && (
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
          <div>
            <label htmlFor="radius_group" className={labelClass}>
              RADIUS group
            </label>
            <input
              id="radius_group"
              className={inputClass}
              value={values.radius_group}
              onChange={(e) => set("radius_group", e.target.value)}
            />
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-3">
        <div>
          <label htmlFor="price" className={labelClass}>
            Price
          </label>
          <input
            id="price"
            className={inputClass}
            inputMode="decimal"
            value={values.price}
            onChange={(e) => set("price", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="duration_days" className={labelClass}>
            Duration (days)
          </label>
          <input
            id="duration_days"
            type="number"
            min={1}
            className={inputClass}
            value={values.duration_days}
            onChange={(e) => set("duration_days", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="quota_gb" className={labelClass}>
            Quota (GB, optional)
          </label>
          <input
            id="quota_gb"
            type="number"
            min={0}
            className={inputClass}
            value={values.quota_gb}
            onChange={(e) => set("quota_gb", e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="bandwidth_down_mbps" className={labelClass}>
            Download (Mbps)
          </label>
          <input
            id="bandwidth_down_mbps"
            type="number"
            min={0}
            className={inputClass}
            value={values.bandwidth_down_mbps}
            onChange={(e) => set("bandwidth_down_mbps", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="bandwidth_up_mbps" className={labelClass}>
            Upload (Mbps)
          </label>
          <input
            id="bandwidth_up_mbps"
            type="number"
            min={0}
            className={inputClass}
            value={values.bandwidth_up_mbps}
            onChange={(e) => set("bandwidth_up_mbps", e.target.value)}
          />
        </div>
      </div>

      <div>
        <label htmlFor="description" className={labelClass}>
          Description (optional)
        </label>
        <textarea
          id="description"
          rows={2}
          className={inputClass}
          value={values.description}
          onChange={(e) => set("description", e.target.value)}
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
        <input
          type="checkbox"
          checked={values.is_active}
          onChange={(e) => set("is_active", e.target.checked)}
        />
        Active
      </label>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Saving…" : mode === "create" ? "Create plan" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/plans")}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
