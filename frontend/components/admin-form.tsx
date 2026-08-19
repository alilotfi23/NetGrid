"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import type { FormEvent } from "react";

import type { Admin, Role } from "@/lib/api";

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50";

const labelClass = "block text-xs font-medium text-zinc-500 dark:text-zinc-400";

/**
 * Create/edit an admin account plus its role assignment. Profile fields PATCH
 * to /api/admins/{id}, then the full role set PUTs to /api/admins/{id}/roles.
 * When editing yourself the role section is hidden: the backend rejects
 * self role changes (self-protection), and it would lock you out of the
 * assignment flow mid-submit.
 */
export function AdminForm({
  admin,
  roles,
  isSelf,
}: {
  admin?: Admin;
  roles: Role[];
  isSelf?: boolean;
}) {
  const mode = admin ? "edit" : "create";
  const router = useRouter();
  const [username, setUsername] = useState(admin?.username ?? "");
  const [email, setEmail] = useState(admin?.email ?? "");
  const [password, setPassword] = useState("");
  const [isActive, setIsActive] = useState(admin?.is_active ?? true);
  const [roleIds, setRoleIds] = useState<number[]>(admin?.roles.map((r) => r.id) ?? []);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function toggleRole(id: number) {
    setRoleIds((prev) =>
      prev.includes(id) ? prev.filter((rid) => rid !== id) : [...prev, id],
    );
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!username.trim()) {
      setError("Username is required");
      return;
    }
    if (!email.trim()) {
      setError("Email is required");
      return;
    }
    if (mode === "create" && password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }
    if (mode === "edit" && password !== "" && password.length < 8) {
      setError("Password must be at least 8 characters");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "create") {
        const res = await fetch("/api/admins", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            username: username.trim(),
            email: email.trim(),
            password,
            is_active: isActive,
            role_ids: roleIds,
          }),
        });
        const body = (await res.json().catch(() => null)) as
          | { error?: string; id?: number }
          | null;
        if (!res.ok) {
          setError(body?.error ?? `Request failed (HTTP ${res.status})`);
          return;
        }
        router.push("/admins");
        router.refresh();
        return;
      }

      // edit: PATCH profile fields, then replace the role set
      const profilePayload: Record<string, unknown> = {
        username: username.trim(),
        email: email.trim(),
        is_active: isActive,
      };
      if (password !== "") profilePayload.password = password;
      const res = await fetch(`/api/admins/${admin!.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profilePayload),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      if (!isSelf) {
        const rolesRes = await fetch(`/api/admins/${admin!.id}/roles`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ role_ids: roleIds }),
        });
        const rolesBody = (await rolesRes.json().catch(() => null)) as
          | { error?: string }
          | null;
        if (!rolesRes.ok) {
          setError(rolesBody?.error ?? `Request failed (HTTP ${rolesRes.status})`);
          return;
        }
      }
      router.push("/admins");
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
          <label htmlFor="admin-username" className={labelClass}>
            Username
          </label>
          <input
            id="admin-username"
            className={inputClass}
            value={username}
            onChange={(e) => setUsername(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="admin-email" className={labelClass}>
            Email
          </label>
          <input
            id="admin-email"
            type="email"
            className={inputClass}
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
      </div>

      <div>
        <label htmlFor="admin-password" className={labelClass}>
          {mode === "create" ? "Password" : "New password (leave blank to keep)"}
        </label>
        <input
          id="admin-password"
          type="password"
          autoComplete="new-password"
          className={inputClass}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />
      </div>

      <label className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
        <input
          type="checkbox"
          checked={isActive}
          onChange={(e) => setIsActive(e.target.checked)}
        />
        Active
      </label>

      {isSelf ? (
        <p className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-2 text-xs text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
          You can&apos;t change your own role assignment (self-protection). Ask
          another admin with <code>admins:manage</code> to adjust your roles.
        </p>
      ) : (
        <fieldset>
          <legend className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
            Roles
          </legend>
          {roles.length === 0 ? (
            <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
              No roles exist yet — create one under Roles first.
            </p>
          ) : (
            <div className="mt-2 grid gap-2 sm:grid-cols-2">
              {roles.map((role) => (
                <label
                  key={role.id}
                  className="flex items-start gap-2 rounded-lg border border-zinc-200 p-3 text-sm dark:border-zinc-800"
                >
                  <input
                    type="checkbox"
                    checked={roleIds.includes(role.id)}
                    onChange={() => toggleRole(role.id)}
                    className="mt-0.5"
                  />
                  <span>
                    <span className="font-medium text-zinc-900 dark:text-zinc-50">
                      {role.name}
                    </span>
                    {role.description && (
                      <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                        {role.description}
                      </span>
                    )}
                  </span>
                </label>
              ))}
            </div>
          )}
        </fieldset>
      )}

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Saving…" : mode === "create" ? "Create admin" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/admins")}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
