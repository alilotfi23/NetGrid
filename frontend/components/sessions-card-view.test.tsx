import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SessionsCardView } from "./sessions-card-view";

describe("SessionsCardView", () => {
  it("renders the total and a per-NAS row with its count", () => {
    render(
      <SessionsCardView
        stats={{
          total: 3,
          by_nas: [
            { nasipaddress: "192.168.0.10", count: 2 },
            { nasipaddress: "192.168.0.11", count: 1 },
          ],
        }}
      />,
    );

    expect(screen.getByRole("heading", { name: "Live Sessions" })).toBeTruthy();
    expect(screen.getByText("3 active")).toBeTruthy();
    expect(screen.getByText("192.168.0.10")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("192.168.0.11")).toBeTruthy();
  });

  it("links the heading to the sessions page", () => {
    render(<SessionsCardView stats={{ total: 0, by_nas: [] }} />);

    const link = within(screen.getByRole("heading", { name: "Live Sessions" })).getByRole("link");
    expect(link.getAttribute("href")).toBe("/sessions");
  });

  it("renders the empty state", () => {
    render(<SessionsCardView stats={{ total: 0, by_nas: [] }} />);

    expect(screen.getByText("No active sessions right now.")).toBeTruthy();
  });

  it("renders the error state instead of counts", () => {
    render(<SessionsCardView error="request failed: HTTP 403" />);

    expect(
      screen.getByRole("heading", { name: "Live sessions unavailable" }),
    ).toBeTruthy();
    expect(screen.getByText("request failed: HTTP 403")).toBeTruthy();
    expect(screen.queryByText("3 active")).toBeNull();
  });
});
