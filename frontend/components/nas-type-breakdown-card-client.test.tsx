import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NasDevicesResult } from "@/lib/api";
import { NasTypeBreakdownCardClient } from "./nas-type-breakdown-card-client";

const INITIAL: NasDevicesResult = {
  ok: true,
  devices: [],
  stats: {
    total: 3,
    active: 3,
    inactive: 0,
    by_type: [
      { nas_type: "mikrotik", count: 2 },
      { nas_type: "cisco", count: 1 },
    ],
  },
};

const NEW: NasDevicesResult = {
  ok: true,
  devices: [],
  stats: {
    total: 4,
    active: 4,
    inactive: 0,
    by_type: [
      { nas_type: "mikrotik", count: 2 },
      { nas_type: "cisco", count: 1 },
      { nas_type: "ubiquiti", count: 1 },
    ],
  },
};

function okJson(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("NasTypeBreakdownCardClient", () => {
  it("renders the server-rendered initial breakdown immediately", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasTypeBreakdownCardClient initial={INITIAL} />);

    expect(screen.getByText("By NAS type")).toBeTruthy();
    // the type names are capitalized via CSS, so match case-insensitively
    expect(screen.getByText(/Mikrotik/i)).toBeTruthy();
    expect(screen.getByText(/Cisco/i)).toBeTruthy();
    expect(screen.queryByText(/Ubiquiti/i)).toBeNull();
  });

  it("polls the route handler and adopts newer breakdowns after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValueOnce(okJson(NEW)) // first interval tick
      .mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    render(<NasTypeBreakdownCardClient initial={INITIAL} />);
    expect(screen.queryByText(/Ubiquiti/i)).toBeNull();
    await act(async () => {}); // flush the mount fetch

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {}); // flush the polled response

    expect(screen.getByText(/Ubiquiti/i)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/nas-stats", expect.anything());
  });

  it("keeps the last known breakdown when a poll fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValue({ ok: false, status: 500 } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<NasTypeBreakdownCardClient initial={INITIAL} />);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText(/Mikrotik/i)).toBeTruthy();
    expect(screen.queryByText("NAS devices by type unavailable")).toBeNull();
  });

  it("renders the error card when the initial load failed", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasTypeBreakdownCardClient initial={{ ok: false, error: "No active session — log in first" }} />);

    expect(screen.getByText("NAS devices by type unavailable")).toBeTruthy();
    expect(screen.getByText("No active session — log in first")).toBeTruthy();
  });
});
