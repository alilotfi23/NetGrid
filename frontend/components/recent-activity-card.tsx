import { loadAuditLogs } from "@/lib/api";
import { RecentActivityClient } from "./recent-activity-client";

const ENTRY_COUNT = 8;

/**
 * Dashboard feed of the latest audit log entries. A server component:
 * fetches the newest entries server-side (token stays out of the browser)
 * and hands them to the polling client as the initial render, so the first
 * paint is instant and the feed then refreshes every 30s. Hidden for roles
 * without audit_logs:read, mirroring the overdue alert's behavior for
 * supplementary cards.
 */
export async function RecentActivityCard() {
  const initial = await loadAuditLogs({ pageSize: ENTRY_COUNT });
  return <RecentActivityClient initial={initial} />;
}
