import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { SessionsResult } from "@/lib/api";
import { SessionsCardClient } from "./sessions-card-client";

const INITIAL: SessionsResult = {
  ok: true,
  sessions: [],
  stats: {
    total: 3,
    by_nas: [{ nasipaddress: "10.0.0.1", count: 3, nas_shortname: "edge-1" }],
  },
};

const NEW: SessionsResult = {
  ok: true,
  sessions: [],
  stats: {
    total: 8,
    by_nas: [
      { nasipaddress: "10.0.0.1", count: 5, nas_shortname: "edge-1" },
      { nasipaddress: "10.0.0.2", count: 3, nas_shortname: "core-1" },
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

describe("SessionsCardClient", () => {
  it("renders the server-rendered initial stats immediately", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SessionsCardClient initial={INITIAL} />);

    expect(screen.getByText("3 active")).toBeTruthy();
    expect(screen.getByText("edge-1")).toBeTruthy();
  });

  it("polls the route handler and adopts newer stats after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValueOnce(okJson(NEW)) // first interval tick
      .mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionsCardClient initial={INITIAL} />);
    expect(screen.getByText("3 active")).toBeTruthy();
    await act(async () => {}); // flush the mount fetch

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {}); // flush the polled response

    expect(screen.getByText("8 active")).toBeTruthy();
    expect(screen.getByText("core-1")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/sessions", expect.anything());
  });

  it("keeps the last known stats when a poll fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValue({ ok: false, status: 500 } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<SessionsCardClient initial={INITIAL} />);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText("3 active")).toBeTruthy();
    expect(screen.queryByText("Live sessions unavailable")).toBeNull();
  });

  it("renders the error card when the initial load failed", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SessionsCardClient initial={{ ok: false, error: "No active session — log in first" }} />);

    expect(screen.getByText("Live sessions unavailable")).toBeTruthy();
    expect(screen.getByText("No active session — log in first")).toBeTruthy();
  });
});
