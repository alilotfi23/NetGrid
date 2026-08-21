"use client";

import type { SessionsResult } from "@/lib/api";
import { useLiveData } from "@/lib/use-live-data";
import { SessionsCardView } from "./sessions-card-view";

const REFRESH_MS = 30_000;

/**
 * Client half of the live-sessions card: starts from the server-rendered
 * `initial` result (instant first paint) and polls the BFF route handler
 * every 30s so session counts stay current without reloading. Failed polls
 * keep the last known data.
 */
export function SessionsCardClient({ initial }: { initial: SessionsResult }) {
  const result = useLiveData<SessionsResult>("/api/dashboard/sessions", initial, REFRESH_MS);

  if (!result.ok) {
    return <SessionsCardView error={result.error} />;
  }
  return <SessionsCardView stats={result.stats} />;
}
