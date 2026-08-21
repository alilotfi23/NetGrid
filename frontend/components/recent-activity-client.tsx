"use client";

import type { AuditLogsResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { RecentActivityView } from "./recent-activity-view";

const REFRESH_MS = 30_000;

/**
 * Client half of the recent-activity feed: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so new entries appear without reloading. Renders nothing when
 * the viewer can't read audit logs — the card reappears automatically if a
 * later poll succeeds. Failed polls keep the last known entries.
 */
export function RecentActivityClient({ initial }: { initial: AuditLogsResult }) {
  const result = useLiveData<AuditLogsResult>("/api/dashboard/activity", initial, REFRESH_MS);

  if (!result.ok) {
    return null;
  }
  return <RecentActivityView entries={result.entries} />;
}
