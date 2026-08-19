import { describe, expect, it } from "vitest";

import {
  formatBytes,
  formatCurrency,
  formatDate,
  formatDay,
  formatDuration,
  formatMonth,
} from "./format";

describe("formatBytes", () => {
  it("formats null as a dash", () => {
    expect(formatBytes(null)).toBe("—");
    expect(formatBytes(undefined)).toBe("—");
  });

  it("formats bytes and SI units", () => {
    expect(formatBytes(512)).toBe("512 B");
    expect(formatBytes(2048)).toBe("2.0 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatBytes(3 * 1024 * 1024 * 1024)).toBe("3.0 GB");
    expect(formatBytes(150 * 1024 * 1024 * 1024)).toBe("150 GB");
  });
});

describe("formatDuration", () => {
  it("formats null as a dash", () => {
    expect(formatDuration(null)).toBe("—");
  });

  it("formats seconds, minutes, and hours", () => {
    expect(formatDuration(45)).toBe("45s");
    expect(formatDuration(125)).toBe("2m 5s");
    expect(formatDuration(3600)).toBe("1h 0m");
    expect(formatDuration(7325)).toBe("2h 2m");
  });
});

describe("formatDate", () => {
  it("formats null and garbage defensively", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate("not-a-date")).toBe("not-a-date");
  });

  it("formats an ISO timestamp", () => {
    const out = formatDate("2026-01-01T12:00:00Z");
    expect(out).toContain("2026");
  });
});

describe("formatCurrency", () => {
  it("formats null as a dash", () => {
    expect(formatCurrency(null)).toBe("—");
    expect(formatCurrency(undefined)).toBe("—");
  });

  it("formats decimal strings and numbers as USD", () => {
    expect(formatCurrency("9.99")).toBe("$9.99");
    expect(formatCurrency("1234.50")).toBe("$1,234.50");
    expect(formatCurrency(0)).toBe("$0.00");
  });

  it("falls back to the raw string on garbage input", () => {
    expect(formatCurrency("abc")).toBe("abc");
  });
});

describe("formatDay", () => {
  it("formats null as a dash", () => {
    expect(formatDay(null)).toBe("—");
  });

  it("formats a date-only string in local time", () => {
    const out = formatDay("2026-03-01");
    expect(out).toContain("Mar");
    expect(out).toContain("1");
    expect(out).toContain("2026");
  });

  it("handles full timestamps and garbage defensively", () => {
    const out = formatDay("2026-01-01T12:00:00Z");
    expect(out).toContain("2026");
    expect(formatDay("not-a-date")).toBe("not-a-date");
  });
});

describe("formatMonth", () => {
  it("formats null as a dash", () => {
    expect(formatMonth(null)).toBe("—");
  });

  it("formats a YYYY-MM bucket", () => {
    expect(formatMonth("2026-08")).toBe("Aug 2026");
    expect(formatMonth("2026-01")).toBe("Jan 2026");
  });

  it("passes through non-bucket strings", () => {
    expect(formatMonth("2026")).toBe("2026");
  });
});
