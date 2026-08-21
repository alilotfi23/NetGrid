import Link from "next/link";

import type { AuditLogEntry } from "@/lib/api";
import { formatRelativeTime } from "@/lib/format";

/** Resources with a detail page the feed can drill into by id. */
const RESOURCE_LINKS: Record<string, string> = {
  subscribers: "/subscribers",
  plans: "/plans",
  nas_devices: "/nas-devices",
  invoices: "/invoices",
  admins: "/admins",
  roles: "/roles",
};

function resourceHref(resource: string, resourceId: string | null): string | null {
  const base = RESOURCE_LINKS[resource];
  if (!base || resourceId == null) return null;
  return `${base}/${resourceId}`;
}

/** Same tone rules as the audit log page's table badges. */
function actionBadge(action: string) {
  const tone = action.includes("delete") || action === "login_failed"
    ? "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
    : action === "login" || action === "create"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : action === "permission_denied"
        ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300";
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}>
      {action}
    </span>
  );
}

/**
 * Presentational feed of the latest audit log entries for the dashboard: a
 * compact list of action badges, drillable resource names, and the actor
 * with a relative timestamp. Rendered only when the viewer can read audit
 * logs (the server card returns null otherwise).
 */
export function RecentActivityView({ entries }: { entries: AuditLogEntry[] }) {
  return (
    <section
      aria-label="Recent activity"
      className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950"
    >
      <div className="flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
          <Link
            href="/audit-logs"
            className="transition-colors hover:text-indigo-600 dark:hover:text-indigo-400"
          >
            Recent activity
          </Link>
        </h2>
        <Link
          href="/audit-logs"
          className="text-xs text-zinc-500 transition-colors hover:text-indigo-600 hover:underline dark:text-zinc-400 dark:hover:text-indigo-400"
        >
          View all
        </Link>
      </div>

      {entries.length === 0 ? (
        <p className="mt-4 text-sm text-zinc-500 dark:text-zinc-400">
          No recent activity yet. Events appear here as admins log in and
          make changes.
        </p>
      ) : (
        <ul className="mt-4 space-y-3">
          {entries.map((entry) => {
            const href = resourceHref(entry.resource, entry.resource_id);
            return (
              <li key={entry.id} className="text-sm">
                <div className="flex min-w-0 items-center gap-2">
                  {actionBadge(entry.action)}
                  {href ? (
                    <Link
                      href={href}
                      className="truncate font-medium text-indigo-600 transition-colors hover:underline dark:text-indigo-400"
                    >
                      {entry.resource}
                      {entry.resource_id != null && (
                        <span className="font-normal text-zinc-400 dark:text-zinc-500">
                          {" "}#{entry.resource_id}
                        </span>
                      )}
                    </Link>
                  ) : (
                    <span className="truncate font-medium text-zinc-700 dark:text-zinc-300">
                      {entry.resource}
                      {entry.resource_id != null && (
                        <span className="font-normal text-zinc-400 dark:text-zinc-500">
                          {" "}#{entry.resource_id}
                        </span>
                      )}
                    </span>
                  )}
                </div>
                <div className="mt-1 text-xs text-zinc-400 dark:text-zinc-500">
                  {entry.admin_id != null ? (
                    <Link
                      href={`/audit-logs?admin_id=${entry.admin_id}`}
                      className="font-medium text-zinc-500 transition-colors hover:text-indigo-600 hover:underline dark:text-zinc-400 dark:hover:text-indigo-400"
                    >
                      {entry.admin_username ?? "system"}
                    </Link>
                  ) : (
                    <span className="text-zinc-400 dark:text-zinc-500">system</span>
                  )}{" "}
                  · {formatRelativeTime(entry.created_at)}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
