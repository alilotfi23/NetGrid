import { AuditLogFilters } from "@/components/audit-log-filters";
import { AuditLogPagination } from "@/components/audit-log-pagination";
import { Nav } from "@/components/nav";
import { type AuditLogEntry, loadAuditLogs } from "@/lib/api";
import { formatDate } from "@/lib/format";

// Live audit data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

/** Compact JSON summary of an entry's metadata, truncated for the table. */
function metadataSummary(entry: AuditLogEntry): string {
  if (entry.metadata_ == null || Object.keys(entry.metadata_).length === 0) return "—";
  const text = JSON.stringify(entry.metadata_);
  return text.length > 70 ? `${text.slice(0, 67)}…` : text;
}

function actionBadge(action: string) {
  const tone = action.includes("delete") || action === "login_failed"
    ? "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300"
    : action === "login" || action === "create"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300"
      : action === "permission_denied"
        ? "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300"
        : "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300";
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${tone}`}
    >
      {action}
    </span>
  );
}

function AuditTable({ entries }: { entries: AuditLogEntry[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Time</th>
            <th className="px-4 py-3 font-medium">Actor</th>
            <th className="px-4 py-3 font-medium">Action</th>
            <th className="px-4 py-3 font-medium">Resource</th>
            <th className="px-4 py-3 font-medium">Details</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {entries.map((entry) => (
            <tr key={entry.id} className="text-zinc-700 dark:text-zinc-300">
              <td className="px-4 py-3 whitespace-nowrap tabular-nums">
                {formatDate(entry.created_at)}
              </td>
              <td className="px-4 py-3 whitespace-nowrap">
                {entry.admin_username ?? (
                  <span className="text-zinc-400 dark:text-zinc-600">system</span>
                )}
              </td>
              <td className="px-4 py-3 whitespace-nowrap">{actionBadge(entry.action)}</td>
              <td className="px-4 py-3 whitespace-nowrap">
                {entry.resource}
                {entry.resource_id != null && (
                  <span className="text-zinc-400 dark:text-zinc-600"> #{entry.resource_id}</span>
                )}
              </td>
              <td className="max-w-xs truncate px-4 py-3 font-mono text-xs text-zinc-500 dark:text-zinc-400">
                <span title={entry.metadata_ != null ? JSON.stringify(entry.metadata_) : undefined}>
                  {metadataSummary(entry)}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Parse a positive integer query param, falling back to a default. */
function intParam(value: string | undefined, fallback: number): number {
  if (value == null) return fallback;
  const parsed = Number(value);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : fallback;
}

export default async function AuditLogsPage({
  searchParams,
}: {
  searchParams: Promise<{
    admin_id?: string;
    action?: string;
    resource?: string;
    page?: string;
    page_size?: string;
  }>;
}) {
  const { admin_id, action, resource, page, page_size } = await searchParams;
  // page_size is clamped to the backend's 1-100 range
  const pageSize = Math.min(100, intParam(page_size, 20));
  const pageNumber = intParam(page, 1);
  const result = await loadAuditLogs({
    adminId: admin_id != null ? intParam(admin_id, 0) : undefined,
    action,
    resource,
    page: pageNumber,
    pageSize,
  });

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Audit Log
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Security-relevant events across the platform — logins, changes,
            payments, and denied permission checks.
          </p>
        </div>

        {!result.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Audit log unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{result.error}</p>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Sign in to the dashboard to refresh the session.
            </p>
          </div>
        ) : (
          <>
            <AuditLogFilters
              filters={result.filters}
              adminId={admin_id}
              action={action}
              resource={resource}
            />

            {result.entries.length === 0 ? (
              <p className="mt-4 rounded-xl border border-zinc-200 bg-white p-5 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
                {result.total > 0
                  ? "No entries match these filters."
                  : "No audit entries yet. Events appear here as admins log in and make changes."}
              </p>
            ) : (
              <div className="mt-4">
                <AuditTable entries={result.entries} />
              </div>
            )}
            <AuditLogPagination
              page={result.page}
              pageSize={result.pageSize}
              total={result.total}
              adminId={admin_id}
              action={action}
              resource={resource}
            />
          </>
        )}
      </div>
    </main>
  );
}
