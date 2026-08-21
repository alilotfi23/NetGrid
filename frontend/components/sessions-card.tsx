import { loadSessions } from "@/lib/api";
import { SessionsCardClient } from "./sessions-card-client";

/**
 * Dashboard card for live sessions. A server component: fetches the backend
 * server-side (token stays out of the browser) and hands the result to the
 * polling client as the initial render, so the first paint is instant and
 * the client then refreshes the session counts every 30s.
 */
export async function SessionsCard() {
  const initial = await loadSessions();
  return <SessionsCardClient initial={initial} />;
}
