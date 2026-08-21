"use client";

import { useEffect, useState } from "react";

/**
 * Refresh cadence for the live dashboard cards. Shared by every polling
 * card so they all stay in sync and one number tunes the whole page.
 */
export const DASHBOARD_REFRESH_MS = 30_000;

/** How often the hook re-renders so staleness flips and the notice advances. */
const TICK_MS = 15_000;

export type LiveDataState<T> = {
  /** The last successfully fetched (or initially rendered) value. */
  data: T;
  /** True when no poll has succeeded for `staleAfterMs` (default: two cycles). */
  stale: boolean;
  /** When the current data was last confirmed by a successful poll. */
  lastUpdatedAt: Date;
};

/**
 * Poll a same-origin route handler every `intervalMs` and keep the last
 * successful response. Used by the dashboard cards to refresh live stats
 * without a page reload: the route handler proxies to the backend with the
 * HttpOnly session cookie, so the token never reaches the browser.
 *
 * Failed polls (network blip, expired session, backend down) keep the last
 * known data — stale-but-visible beats flashing error cards every 30s — so
 * the error state only ever comes from the `initial` value, which the server
 * component computed at render time. `stale` goes true once no poll has
 * succeeded for `staleAfterMs`, letting cards show a subtle "updated Xs ago"
 * caption; a slow re-render ticker keeps that caption advancing.
 */
export function useLiveData<T>(
  path: string,
  initial: T,
  intervalMs: number,
  staleAfterMs: number = intervalMs * 2,
): LiveDataState<T> {
  const [state, setState] = useState({ data: initial, lastUpdatedAt: new Date() });
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const res = await fetch(path, { cache: "no-store" });
        if (!res.ok) return; // keep the last known data
        const next = (await res.json()) as T;
        if (!cancelled) setState({ data: next, lastUpdatedAt: new Date() });
      } catch {
        // transient failure — keep the last known data
      }
    };

    load();
    const id = setInterval(load, intervalMs);
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [path, intervalMs]);

  // Re-render on a slow cadence so staleness is detected even while every
  // poll fails. `now` lives in state so the render stays pure (no Date.now).
  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), TICK_MS);
    return () => clearInterval(id);
  }, []);

  const stale = now.getTime() - state.lastUpdatedAt.getTime() > staleAfterMs;
  return { data: state.data, stale, lastUpdatedAt: state.lastUpdatedAt };
}
