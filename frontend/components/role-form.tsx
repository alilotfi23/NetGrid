"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { FormEvent } from "react";

import type { Permission, Role } from "@/lib/api";
import { permissionLabel } from "@/lib/format";

const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-50";

const labelClass = "block text-xs font-medium text-zinc-500 dark:text-zinc-400";

function groupPermissions(permissions: Permission[]): Map<string, Permission[]> {
  const groups = new Map<string, Permission[]>();
  for (const permission of permissions) {
    const resource = permission.code.split(":")[0] ?? permission.code;
    const list = groups.get(resource) ?? [];
    list.push(permission);
    groups.set(resource, list);
  }
  return groups;
}

/**
 * Create/edit a role plus its permission set. Profile fields PATCH to
 * /api/roles/{id}, then the full permission-code set PUTs to
 * /api/roles/{id}/permissions (which invalidates every member's cache).
 */
export function RoleForm({ role, permissions }: { role?: Role; permissions: Permission[] }) {
  const mode = role ? "edit" : "create";
  const router = useRouter();
  const [name, setName] = useState(role?.name ?? "");
  const [description, setDescription] = useState(role?.description ?? "");
  const [codes, setCodes] = useState<string[]>(role?.permissions.map((p) => p.code) ?? []);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  // stable group order: wildcards first, then resources alphabetically
  const groups = useMemo(() => {
    const grouped = groupPermissions(permissions);
    return [...grouped.entries()].sort(([a], [b]) => {
      if (a === "*") return -1;
      if (b === "*") return 1;
      return a.localeCompare(b);
    });
  }, [permissions]);

  function toggleCode(code: string) {
    setCodes((prev) => (prev.includes(code) ? prev.filter((c) => c !== code) : [...prev, code]));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);

    if (!name.trim()) {
      setError("Name is required");
      return;
    }

    setSubmitting(true);
    try {
      if (mode === "create") {
        const res = await fetch("/api/roles", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
            description: description.trim() === "" ? null : description.trim(),
            permission_codes: codes,
          }),
        });
        const body = (await res.json().catch(() => null)) as { error?: string } | null;
        if (!res.ok) {
          setError(body?.error ?? `Request failed (HTTP ${res.status})`);
          return;
        }
        router.push("/roles");
        router.refresh();
        return;
      }

      // edit: PATCH profile fields, then replace the permission set
      const res = await fetch(`/api/roles/${role!.id}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: name.trim(),
          description: description.trim() === "" ? null : description.trim(),
        }),
      });
      const body = (await res.json().catch(() => null)) as { error?: string } | null;
      if (!res.ok) {
        setError(body?.error ?? `Request failed (HTTP ${res.status})`);
        return;
      }
      const permsRes = await fetch(`/api/roles/${role!.id}/permissions`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ permission_codes: codes }),
      });
      const permsBody = (await permsRes.json().catch(() => null)) as { error?: string } | null;
      if (!permsRes.ok) {
        setError(permsBody?.error ?? `Request failed (HTTP ${permsRes.status})`);
        return;
      }
      router.push("/roles");
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
          <label htmlFor="role-name" className={labelClass}>
            Name
          </label>
          <input
            id="role-name"
            className={inputClass}
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor="role-description" className={labelClass}>
            Description (optional)
          </label>
          <input
            id="role-description"
            className={inputClass}
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </div>
      </div>

      <fieldset>
        <legend className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
          Permissions ({codes.length} selected)
        </legend>
        {permissions.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500 dark:text-zinc-400">
            No permissions in the catalog yet.
          </p>
        ) : (
          <div className="mt-2 space-y-4">
            {groups.map(([resource, perms]) => (
              <div key={resource}>
                <h3 className="text-xs font-semibold uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
                  {resource === "*" ? "Wildcard" : resource}
                </h3>
                <div className="mt-1.5 grid gap-2 sm:grid-cols-2">
                  {perms.map((permission) => (
                    <label
                      key={permission.id}
                      className="flex items-start gap-2 rounded-lg border border-zinc-200 p-2.5 text-sm dark:border-zinc-800"
                    >
                      <input
                        type="checkbox"
                        aria-label={permission.code}
                        checked={codes.includes(permission.code)}
                        onChange={() => toggleCode(permission.code)}
                        className="mt-0.5"
                      />
                      <span>
                        <span className="font-mono text-xs text-zinc-900 dark:text-zinc-50">
                          {permissionLabel(permission.code)}
                        </span>
                        {permission.description && (
                          <span className="block text-xs text-zinc-500 dark:text-zinc-400">
                            {permission.description}
                          </span>
                        )}
                      </span>
                    </label>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </fieldset>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500 disabled:opacity-50"
        >
          {submitting ? "Saving…" : mode === "create" ? "Create role" : "Save changes"}
        </button>
        <button
          type="button"
          onClick={() => router.push("/roles")}
          className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
        >
          Cancel
        </button>
      </div>
    </form>
  );
}
