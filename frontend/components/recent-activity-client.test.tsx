import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { AuditLogEntry, AuditLogsResult } from "@/lib/api";
import { RecentActivityClient } from "./recent-activity-client";

function entry(id: number, username: string): AuditLogEntry {
  return {
    id,
    admin_id: 1,
    admin_username: username,
    action: "create",
    resource: "subscribers",
    resource_id: String(id),
    metadata_: null,
    created_at: new Date(Date.now() - id * 60 * 1000).toISOString(),
  };
}

function result(entries: AuditLogEntry[]): AuditLogsResult {
  return {
    ok: true,
    entries,
    filters: { actions: [], resources: [], admins: [] },
    total: entries.length,
    page: 1,
    pageSize: 8,
  };
}

const INITIAL = result([entry(1, "superadmin")]);
const NEW = result([entry(2, "billing"), entry(1, "superadmin")]);

function okJson(body: unknown): Response {
  return { ok: true, json: async () => body } as Response;
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.useRealTimers();
});

describe("RecentActivityClient", () => {
  it("renders the server-rendered initial entries immediately", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<RecentActivityClient initial={INITIAL} />);

    expect(screen.getByText("create")).toBeTruthy();
    expect(screen.getByText(/subscribers/)).toBeTruthy();
    expect(screen.getByText(/superadmin/)).toBeTruthy();
  });

  it("polls the route handler and adopts newer entries after the interval", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValueOnce(okJson(NEW)) // first interval tick
      .mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    render(<RecentActivityClient initial={INITIAL} />);
    expect(screen.queryByText(/billing/)).toBeNull();
    await act(async () => {}); // flush the mount fetch

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {}); // flush the polled response

    expect(screen.getByText(/billing/)).toBeTruthy();
    expect(fetchMock).toHaveBeenCalledWith("/api/dashboard/activity", expect.anything());
  });

  it("keeps the last known entries when a poll fails", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(okJson(INITIAL)) // mount fetch
      .mockResolvedValue({ ok: false, status: 500 } as Response);
    vi.stubGlobal("fetch", fetchMock);

    render(<RecentActivityClient initial={INITIAL} />);
    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText(/superadmin/)).toBeTruthy();
  });

  it("stops polling after unmount", async () => {
    vi.useFakeTimers();
    const fetchMock = vi.fn().mockResolvedValue(okJson(INITIAL));
    vi.stubGlobal("fetch", fetchMock);

    const { unmount } = render(<RecentActivityClient initial={INITIAL} />);
    await act(async () => {}); // flush the mount fetch
    unmount();

    const callsAtUnmount = fetchMock.mock.calls.length;
    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });
    expect(fetchMock.mock.calls.length).toBe(callsAtUnmount);
  });

  it("renders nothing when the initial load failed, but appears once a poll succeeds", async () => {
    vi.useFakeTimers();
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce({ ok: false, status: 500 } as Response) // mount fetch
      .mockResolvedValue(okJson(INITIAL)); // first interval tick
    vi.stubGlobal("fetch", fetchMock);

    const { container } = render(
      <RecentActivityClient initial={{ ok: false, error: "No active session — log in first" }} />,
    );
    expect(container.innerHTML).toBe("");

    await act(async () => {
      vi.advanceTimersByTime(30_000);
    });
    await act(async () => {});

    expect(screen.getByText(/superadmin/)).toBeTruthy();
  });
});
