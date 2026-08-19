import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { NasTypeBreakdownView } from "./nas-type-breakdown-view";

describe("NasTypeBreakdownView", () => {
  it("renders a row per NAS type with its count", () => {
    render(
      <NasTypeBreakdownView
        byType={[
          { nas_type: "mikrotik", count: 3 },
          { nas_type: "cisco", count: 1 },
        ]}
      />,
    );

    expect(screen.getByRole("heading", { name: "By NAS type" })).toBeTruthy();
    expect(screen.getByText("mikrotik")).toBeTruthy();
    expect(screen.getByText("3")).toBeTruthy();
    expect(screen.getByText("cisco")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
  });

  it("scales the bar width proportionally to the largest count", () => {
    render(<NasTypeBreakdownView byType={[{ nas_type: "other", count: 4 }]} />);

    const bar = screen.getByText("other").closest("li")?.querySelector("div > div");
    expect(bar).toHaveProperty("style.width", "100%");
  });

  it("renders the empty state when there are no devices", () => {
    render(<NasTypeBreakdownView byType={[]} />);

    expect(screen.getByText("No NAS devices yet.")).toBeTruthy();
  });

  it("renders the error state", () => {
    render(<NasTypeBreakdownView error="request failed: HTTP 403" />);

    expect(
      screen.getByRole("heading", { name: "NAS devices by type unavailable" }),
    ).toBeTruthy();
    expect(screen.getByText("request failed: HTTP 403")).toBeTruthy();
  });
});
