import { act, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { StatsResult, SubscriberStats } from "@/lib/api";
import { StatsCardClient } from "./stats-card-client";

// PlanBreakdownChart uses the router to drill down to filtered lists.
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

const STATS: SubscriberStats = {
  active: 2,
  suspended: 1,
  expired: 1,
  total: 4,
  by_plan: [{ plan_id: 1, plan_name: "Starter", count: 2 }],
  by_plan_status: [{ plan_id: 1, plan_name: "Starter", status: "active", count: 2 }],
};

const INITIAL: StatsResult = { ok: true, stats: STATS };
const NEW: StatsResult = { ok: true, stats: { ...STATS, active: 7, total: 9 } };

function okJson(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("StatsCardClient", () => {
  it("renders the server-rendered initial stats immediately", () => {
    vi.stubGlobal("fetch", vi.fn());
    const { container } = render(<StatsCardClient initial={INITIAL} />);

    const dl = container.querySelector("dl");
    expect(within(dl as HTMLElement).getByText("Active")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("2")).toBeTruthy();
    expect(within(dl as HTMLElement).getByText("4")).toBeTruthy();
  });

  it("polls the route handler and adopts newer stats after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValueOnce(okJson(NEW)) // first interval tick
      .mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    render(<StatsCardClient initial={INITIAL} />);
    await act(async () => {}); // flush the mount fetch

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {}); // flush the polled response

    expect(screen.getByText("7")).toBeTruthy();
    expect(screen.getByText("9 total")).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/subscriber-stats", expect.anything());
  });

  it("keeps the last known stats when a poll fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValue({ ok: false, status: 500 } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<StatsCardClient initial={INITIAL} />);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText("4 total")).toBeTruthy();
    expect(screen.queryByText("Subscriber stats unavailable")).toBeNull();
  });

  it("shows a stale caption once polls stop succeeding", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 500 } as Response));

    render(<StatsCardClient initial={INITIAL} />);
    expect(screen.queryByText(/Updated/)).toBeNull();

    await act(async () => {
      vi.advanceTimersByTime(90_000);
    });
    await act(async () => {});

    expect(screen.getByText(/Updated/)).toBeTruthy();
  });

  it("renders the error card when the initial load failed", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<StatsCardClient initial={{ ok: false, error: "No active session — log in first" }} />);

    expect(screen.getByText("Subscriber stats unavailable")).toBeTruthy();
    expect(screen.getByText("No active session — log in first")).toBeTruthy();
  });
});
