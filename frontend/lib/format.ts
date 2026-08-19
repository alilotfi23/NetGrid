/** Display formatting helpers for the dashboard (pure, unit-testable). */

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = -1;
  do {
    value /= 1024;
    unit += 1;
  } while (value >= 1024 && unit < units.length - 1);
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  if (seconds < 60) return `${seconds}s`;
  const h = Math.floor(seconds / 3600);
  const m = Math.floor((seconds % 3600) / 60);
  const s = seconds % 60;
  if (h === 0) return `${m}m ${s}s`;
  return `${h}h ${m}m`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

/**
 * Format a date-only "YYYY-MM-DD" string as a readable day, e.g. "Mar 1, 2026".
 * Falls back to formatDate's behavior for full timestamps and raw strings for
 * garbage input. Date-only strings are parsed in local time to avoid UTC
 * off-by-one rendering.
 */
export function formatDay(iso: string | null | undefined): string {
  if (!iso) return "—";
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (match) {
    const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
    return date.toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("en-US");
}

/**
 * Format a decimal amount (backend serializes Decimals as strings, e.g.
 * "9.99") as a USD amount. Falls back to the raw string on garbage input.
 */
export function formatCurrency(value: string | number | null | undefined): string {
  if (value == null) return "—";
  const num = typeof value === "number" ? value : Number(value);
  if (Number.isNaN(num)) return String(value);
  return num.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

/** Permission code minus its resource prefix, e.g. "subscribers:write" -> "write". */
export function permissionLabel(code: string): string {
  const colon = code.indexOf(":");
  return colon >= 0 ? code.slice(colon + 1) : code;
}

/** Format a "YYYY-MM" report bucket as a readable month, e.g. "Aug 2026". */
export function formatMonth(month: string | null | undefined): string {
  if (!month) return "—";
  const match = /^(\d{4})-(\d{2})$/.exec(month);
  if (!match) return month;
  const date = new Date(Number(match[1]), Number(match[2]) - 1, 1);
  if (Number.isNaN(date.getTime())) return month;
  return date.toLocaleString("en-US", { month: "short", year: "numeric" });
}
