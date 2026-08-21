import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NasDevicesResult } from "@/lib/api";
import { NasStatsCardClient } from "./nas-stats-card-client";

const INITIAL: NasDevicesResult = {
  ok: true,
  devices: [],
  stats: { total: 5, active: 3, inactive: 2, by_type: [] },
};

const NEW: NasDevicesResult = {
  ok: true,
  devices: [],
  stats: { total: 8, active: 6, inactive: 2, by_type: [] },
};

function okJson(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("NasStatsCardClient", () => {
  it("renders the server-rendered initial stats immediately", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasStatsCardClient initial={INITIAL} />);

    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("3 of 5 active")).toBeTruthy();
  });

  it("polls the route handler and adopts newer stats after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValueOnce(okJson(NEW)) // first interval tick
      .mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    render(<NasStatsCardClient initial={INITIAL} />);
    await act(async () => {}); // flush the mount fetch

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {}); // flush the polled response

    expect(screen.getByText("8")).toBeTruthy();
    expect(screen.getByText("6 of 8 active")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/nas-stats", expect.anything());
  });

  it("keeps the last known stats when a poll fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValue({ ok: false, status: 500 } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<NasStatsCardClient initial={INITIAL} />);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText("3 of 5 active")).toBeTruthy();
    expect(screen.queryByText("NAS devices unavailable")).toBeNull();
  });

  it("renders the error card when the initial load failed", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasStatsCardClient initial={{ ok: false, error: "No active session — log in first" }} />);

    expect(screen.getByText("NAS devices unavailable")).toBeTruthy();
    expect(screen.getByText("No active session — log in first")).toBeTruthy();
  });
});
