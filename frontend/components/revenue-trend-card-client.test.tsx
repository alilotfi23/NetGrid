import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RevenueTrendResult } from "@/lib/api";
import type { RevenueTrendPoint } from "@/lib/revenue-trend";
import { RevenueTrendCardClient } from "./revenue-trend-card-client";

// The view's bars navigate on click.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Trailing 12 months ending Aug 2026, oldest first.
const MONTHS = [
  "2025-09", "2025-10", "2025-11", "2025-12",
  "2026-01", "2026-02", "2026-03", "2026-04",
  "2026-05", "2026-06", "2026-07", "2026-08",
];

function points(revenues: Record<string, string>): RevenueTrendPoint[] {
  return MONTHS.map((month) => ({ month, revenue: revenues[month] ?? "0.00" }));
}

const INITIAL: RevenueTrendResult = { ok: true, points: points({ "2026-08": "100.00" }) };
const NEW: RevenueTrendResult = {
  ok: true,
  points: points({ "2026-08": "250.00", "2026-07": "50.00" }),
};

function okJson(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("RevenueTrendCardClient", () => {
  it("renders the server-rendered initial series immediately", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<RevenueTrendCardClient initial={INITIAL} />);

    expect(screen.getByText("Revenue trend")).toBeTruthy();
    expect(screen.getByText("$100.00")).toBeTruthy();
  });

  it("polls the route handler and adopts newer points after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValueOnce(okJson(NEW)) // first interval tick
      .mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    render(<RevenueTrendCardClient initial={INITIAL} />);
    expect(screen.getByText("$100.00")).toBeTruthy();
    await act(async () => {}); // flush the mount fetch

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {}); // flush the polled response

    expect(screen.getByText("$300.00")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/revenue-trend", expect.anything());
  });

  it("keeps the last known series when a poll fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValue({ ok: false, status: 500 } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<RevenueTrendCardClient initial={INITIAL} />);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText("$100.00")).toBeTruthy();
    expect(screen.queryByText("Revenue trend unavailable")).toBeNull();
  });

  it("renders the error card when the initial load failed", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<RevenueTrendCardClient initial={{ ok: false, error: "No active session — log in first" }} />);

    expect(screen.getByText("Revenue trend unavailable")).toBeTruthy();
    expect(screen.getByText("No active session — log in first")).toBeTruthy();
  });
});
