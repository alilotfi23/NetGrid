import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NasStatsCardView } from "./nas-stats-card-view";

describe("NasStatsCardView", () => {
  it("renders the total, active and inactive counts", () => {
    render(<NasStatsCardView stats={{ total: 5, active: 3, inactive: 2, by_type: [] }} />);

    expect(screen.getByRole("heading", { name: "NAS Devices" })).toBeTruthy();
    expect(screen.getByText("5")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("3 of 5 active")).toBeTruthy();
  });

  it("links the heading to the NAS devices list", () => {
    render(<NasStatsCardView stats={{ total: 5, active: 3, inactive: 2, by_type: [] }} />);

    const link = within(screen.getByRole("heading", { name: "NAS Devices" })).getByRole("link");
    expect(link.getAttribute("href")).toBe("/nas-devices");
  });

  it("renders zeroes for an empty inventory", () => {
    render(<NasStatsCardView stats={{ total: 0, active: 0, inactive: 0, by_type: [] }} />);

    expect(screen.getByText("0 of 0 active")).toBeTruthy();
    expect(screen.getAllByText("0")).toHaveLength(3);
  });

  it("renders the error state instead of counts", () => {
    render(<NasStatsCardView error="NAS devices unavailable" />);

    expect(screen.getByRole("heading", { name: "NAS devices unavailable" })).toBeTruthy();
    expect(screen.getByRole("region", { name: "NAS device stats" })).toHaveProperty(
      "textContent",
      expect.stringContaining("NAS devices unavailable"),
    );
    expect(screen.queryByText("3 of 5 active")).toBeNull();
  });
});
