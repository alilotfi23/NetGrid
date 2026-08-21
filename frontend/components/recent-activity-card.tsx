import { loadAuditLogs } from "@/lib/api";
import { RecentActivityView } from "./recent-activity-view";

const ENTRY_COUNT = 8;

/**
 * Dashboard feed of the latest audit log entries. A server component:
 * fetches the newest entries server-side (token stays out of the browser).
 * Returns nothing when the caller can't read audit logs (missing
 * audit_logs:read or an expired session), mirroring the overdue alert's
 * behavior for supplementary cards.
 */
export async function RecentActivityCard() {
  const result = await loadAuditLogs({ pageSize: ENTRY_COUNT });
  if (!result.ok) return null;
  return <RecentActivityView entries={result.entries} />;
}
