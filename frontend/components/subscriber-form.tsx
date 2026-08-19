"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import type { Plan, Subscriber } from "@/lib/api";

type SubscriberFormValues = {
  username: string;
  full_name: string;
  email: string;
  phone: string;
  password: string;
  status: string;
  plan_id: string;
  notes: string;
};

function initialValues(subscriber?: Subscriber): SubscriberFormValues {
  return {
    username: subscriber?.username ?? "",
    full_name: subscriber?.full_name ?? "",
    email: subscriber?.email ?? "",
    phone: subscriber?.phone ?? "",
    password: "",
    status: subscriber?.status ?? "active",
    plan_id: subscriber?.plan_id != null ? String(subscriber.plan_id) : "",
    notes: subscriber?.notes ?? "",
  };
}

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50";

const labelClass = "block text-xs font-medium text-zinc-500 dark:text-zinc-400";

export function SubscriberForm({
  subscriber,
  plans,
}: {
  subscriber?: Subscriber;
  plans: Plan[];
}) {
  const mode = subscriber ? "edit" : "create";
  const router = useRouter();
  const [values, setValues] = useState<SubscriberFormValues>(() => initialValues(subscriber));
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function set<K extends keyof SubscriberFormValues>(key: K, value: SubscriberFormValues[K]) {
    setValues((prev) => ({ ...prev, [key]: value }));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!values.full_name.trim()) {
      setError("Full name is required");
      return;
    }
    if (mode === "create") {
      if (!values.username.trim()) {
        setError("Username is required");
        return;
      }
      if (values.password.length < 8) {
        setError("Password must be at least 8 characters");
        return;
      }
    }

    const planId = values.plan_id === "" ? null : Number(values.plan_id);
    const base = {
      full_name: values.full_name.trim(),
      email: values.email.trim() === "" ? null : values.email.trim(),
      phone: values.phone.trim() === "" ? null : values.phone.trim(),
      status: values.status,
      plan_id: planId,
      notes: values.notes.trim() === "" ? null : values.notes.trim(),
    };
    const payload = mode === "create" ? { ...base, username: values.username.trim(), password: values.password } : base;

    setSubmitting(true);
    try {
      const res = await fetch(subscriber ? `/api/subscribers/${subscriber.id}` : "/api/subscribers", {
        method: subscriber ? "PATCH" : "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      router.push(`/subscribers/${subscriber ? subscriber.id : (body as { id?: number }).id}`);
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
            <label htmlFor="username" className={labelClass}>
              Username
            </label>
            <input
              id="username"
              className={inputClass}
              value={values.username}
              onChange={(e) => set("username", e.target.value)}
            />
          </div>
          <div>
            <label htmlFor="password" className={labelClass}>
              Password
            </label>
            <input
              id="password"
              type="password"
              className={inputClass}
              value={values.password}
              onChange={(e) => set("password", e.target.value)}
            />
          </div>
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="full_name" className={labelClass}>
            Full name
          </label>
          <input
            id="full_name"
            className={inputClass}
            value={values.full_name}
            onChange={(e) => set("full_name", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="email" className={labelClass}>
            Email (optional)
          </label>
          <input
            id="email"
            type="email"
            className={inputClass}
            value={values.email}
            onChange={(e) => set("email", e.target.value)}
          />
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="phone" className={labelClass}>
            Phone (optional)
          </label>
          <input
            id="phone"
            className={inputClass}
            value={values.phone}
            onChange={(e) => set("phone", e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="plan_id" className={labelClass}>
            Plan
          </label>
          <select
            id="plan_id"
            className={inputClass}
            value={values.plan_id}
            onChange={(e) => set("plan_id", e.target.value)}
          >
            <option value="">No plan</option>
            {plans.map((plan) => (
              <option key={plan.id} value={plan.id}>
                {plan.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor="status" className={labelClass}>
            Status
          </label>
          <select
            id="status"
            className={inputClass}
            value={values.status}
            onChange={(e) => set("status", e.target.value)}
          >
            <option value="active">Active</option>
            <option value="suspended">Suspended</option>
            <option value="expired">Expired</option>
          </select>
        </div>
        <div>
          <label htmlFor="notes" className={labelClass}>
            Notes (optional)
          </label>
          <input
            id="notes"
            className={inputClass}
            value={values.notes}
            onChange={(e) => set("notes", e.target.value)}
          />
        </div>
      </div>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Saving…" : mode === "create" ? "Create subscriber" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={() => router.push(subscriber ? `/subscribers/${subscriber.id}` : "/subscribers")}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
