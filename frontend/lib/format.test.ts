import { describe, expect, it } from "vitest";

import { formatBytes, formatDate, formatDuration } from "./format";

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
