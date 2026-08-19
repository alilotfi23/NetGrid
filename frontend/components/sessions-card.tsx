import { loadSessions } from "@/lib/api";
import { SessionsCardView } from "./sessions-card-view";

/**
 * Dashboard card for live sessions. A server component: fetches the backend
 * server-side (token stays out of the browser) and renders the presentational
 * view with either data or an error state.
 */
export async function SessionsCard() {
  const result = await loadSessions();
  if (!result.ok) {
    return <SessionsCardView error={result.error} />;
  }
  return <SessionsCardView stats={result.stats} />;
}
