"use client";

import type { SessionsResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { SessionsCardView } from "./sessions-card-view";
import { StaleNotice } from "./stale-notice";

const REFRESH_MS = 30_000;

/**
 * Client half of the live-sessions card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so session counts stay current without reloading. Failed polls
 * keep the last known data and surface a subtle stale caption once they've
 * been missing a while.
 */
export function SessionsCardClient({ initial }: { initial: SessionsResult }) {
  const { data: result, stale, lastUpdatedAt } = useLiveData<SessionsResult>(
    "/api/dashboard/sessions",
    initial,
    REFRESH_MS,
  );

  return (
    <>
      {result.ok ? <SessionsCardView stats={result.stats} /> : <SessionsCardView error={result.error} />}
      {result.ok && stale && <StaleNotice lastUpdatedAt={lastUpdatedAt} />}
    </>
  );
}
