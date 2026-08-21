import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { DashboardKpisResult } from "@/lib/api";
import { DashboardKpisClient } from "./dashboard-kpis-client";

const INITIAL: DashboardKpisResult = {
  ok: true,
  kpis: {
    activeSubscribers: 10,
    liveSessions: 3,
    revenueYearToDate: "100.00",
    overdueCount: 1,
    overdueAmount: "50.00",
  },
};

const NEW: DashboardKpisResult = {
  ok: true,
  kpis: { ...INITIAL.kpis, activeSubscribers: 42, liveSessions: 9 },
};

function okJson(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("DashboardKpisClient", () => {
  it("renders the server-rendered initial stats immediately", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<DashboardKpisClient initial={INITIAL} />);

    expect(screen.getByText("10")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("$100.00")).toBeTruthy();
    expect(screen.getByText("$50.00")).toBeTruthy();
  });

  it("polls the route handler and adopts newer stats after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValueOnce(okJson(NEW)) // first interval tick
      .mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardKpisClient initial={INITIAL} />);
    expect(screen.getByText("10")).toBeTruthy();
    await act(async () => {}); // flush the mount fetch

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {}); // flush the polled response

    expect(screen.getByText("42")).toBeTruthy();
    expect(screen.getByText("9")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/kpis", expect.anything());
  });

  it("keeps the last known stats when a poll fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValue({ ok: false, status: 500 } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<DashboardKpisClient initial={INITIAL} />);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText("10")).toBeTruthy();
    expect(screen.queryByText("Dashboard stats unavailable")).toBeNull();
  });

  it("stops polling after unmount", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    const { unmount } = render(<DashboardKpisClient initial={INITIAL} />);
    await act(async () => {}); // flush the mount fetch
    unmount();

    const callsAtUnmount = fetchMock.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(fetchMock.mock.calls.length).toBe(callsAtUnmount);
  });

  it("renders the error card when the initial load failed", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<DashboardKpisClient initial={{ ok: false, error: "No active session — log in first" }} />);

    expect(screen.getByText("Dashboard stats unavailable")).toBeTruthy();
    expect(screen.getByText("No active session — log in first")).toBeTruthy();
  });
});
