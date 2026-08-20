"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import type { AuditLogFilters } from "@/lib/api";

type Props = {
  /** Distinct filter values present in the log (from the API response). */
  filters: AuditLogFilters;
  adminId?: string;
  action?: string;
  resource?: string;
};

const selectClass =
  "rounded-lg border border-zinc-300 bg-white px-2.5 py-1.5 text-xs font-medium " +
  "text-zinc-700 focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 " +
  "dark:border-zinc-700 dark:bg-zinc-950 dark:text-zinc-300";

type Field = "adminId" | "action" | "resource";

/**
 * Actor / action / resource filters for the audit log. Navigating (a server
 * round trip) keeps the trail server-rendered; each select preserves the
 * other two filters, and a Reset link appears whenever any filter is active.
 */
export function AuditLogFilters({ filters, adminId, action, resource }: Props) {
  const router = useRouter();
  const current: Record<Field, string> = {
    adminId: adminId ?? "",
    action: action ?? "",
    resource: resource ?? "",
  };
  const hasFilters = Object.values(current).some(Boolean);

  function navigate(next: Record<Field, string>) {
    const params = new URLSearchParams();
    if (next.adminId) params.set("admin_id", next.adminId);
    if (next.action) params.set("action", next.action);
    if (next.resource) params.set("resource", next.resource);
    const qs = params.toString();
    router.push(`/audit-logs${qs ? `?${qs}` : ""}`);
  }

  function onChange(field: Field, value: string) {
    navigate({ ...current, [field]: value });
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <label className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Actor</span>
        <select
          aria-label="Filter by actor"
          value={current.adminId}
          onChange={(e) => onChange("adminId", e.target.value)}
          className={selectClass}
        >
          <option value="">All actors</option>
          {filters.admins.map((admin) => (
            <option key={admin.id} value={admin.id}>
              {admin.username}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Action</span>
        <select
          aria-label="Filter by action"
          value={current.action}
          onChange={(e) => onChange("action", e.target.value)}
          className={selectClass}
        >
          <option value="">All actions</option>
          {filters.actions.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>

      <label className="flex items-center gap-2">
        <span className="text-xs text-zinc-500 dark:text-zinc-400">Resource</span>
        <select
          aria-label="Filter by resource"
          value={current.resource}
          onChange={(e) => onChange("resource", e.target.value)}
          className={selectClass}
        >
          <option value="">All resources</option>
          {filters.resources.map((item) => (
            <option key={item} value={item}>
              {item}
            </option>
          ))}
        </select>
      </label>

      {hasFilters && (
        <Link
          href="/audit-logs"
          className="text-xs text-indigo-600 transition-colors hover:underline dark:text-indigo-400"
        >
          Reset filters
        </Link>
      )}
    </div>
  );
}
