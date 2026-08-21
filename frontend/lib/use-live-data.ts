"use client";

import { useEffect, useState } from "react";

/**
 * Poll a same-origin route handler every `intervalMs` and keep the last
 * successful response. Used by the dashboard cards to refresh live stats
 * without a page reload: the route handler proxies to the backend with the
 * HttpOnly session cookie, so the token never reaches the browser.
 *
 * Failed polls (network blip, expired session, backend down) keep the last
 * known data — stale-but-visible beats flashing error cards every 30s — so
 * the error state only ever comes from the `initial` value, which the server
 * component computed at render time.
 */
export function useLiveData<T>(path: string, initial: T, intervalMs: number): T {
  const [data, setData] = useState<T>(initial);

  useEffect(() => {
    let cancelled = false;

    const load = async () => {
      try {
        const res = await fetch(path, { cache: "no-store" });
        if (!res.ok) return; // keep the last known data
        const next = (await res.json()) as T;
        if (!cancelled) setData(next);
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

  return data;
}
