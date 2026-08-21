import { act, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { StaleNotice } from "./stale-notice";

afterEach(() => {
  vi.useRealTimers();
});

describe("StaleNotice", () => {
  it("shows the time since the last successful update", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-21T12:00:00Z"));

    render(<StaleNotice lastUpdatedAt={new Date("2026-08-21T11:58:00Z")} />);

    expect(screen.getByText(/Updated 2m ago/)).toBeTruthy();
  });

  it("advances the relative time on its own tick", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-21T12:00:00Z"));

    render(<StaleNotice lastUpdatedAt={new Date("2026-08-21T11:59:00Z")} />);
    expect(screen.getByText(/Updated 1m ago/)).toBeTruthy();

    await act(async () => {
      vi.advanceTimersByTime(60_000);
    });

    expect(screen.getByText(/Updated 2m ago/)).toBeTruthy();
  });
});
