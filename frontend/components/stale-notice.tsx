"use client";

import { useEffect, useState } from "react";

import { formatRelativeTime } from "@/lib/format";

/** How often the caption re-evaluates its relative time. */
const TICK_MS = 15_000;

/**
 * Subtle staleness caption for the live dashboard cards: "Updated 2m ago",
 * re-evaluated every 15s so the relative time keeps advancing while polls
 * are failing. Rendered by the polling card clients only when their data is
 * actually stale.
 */
export function StaleNotice({ lastUpdatedAt }: { lastUpdatedAt: Date }) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), TICK_MS);
    return () => clearInterval(id);
  }, []);

  return (
    <p className="mt-2 text-right text-xs text-zinc-400 dark:text-zinc-500">
      Updated {formatRelativeTime(lastUpdatedAt.toISOString(), now)}
    </p>
  );
}
