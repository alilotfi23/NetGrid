import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NasDeviceDeleteButton } from "./nas-device-delete-button";

const { refreshMock } = vi.hoisted(() => ({
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), refresh: refreshMock }),
}));

afterEach(() => {
  vi.unstubAllGlobals();
  refreshMock.mockClear();
});

describe("NasDeviceDeleteButton", () => {
  it("opens a confirmation dialog naming the device", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasDeviceDeleteButton deviceId={3} deviceName="edge-r1" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("Delete NAS device?");
    expect(dialog.textContent).toContain("edge-r1");
    expect(dialog.textContent).toContain("FreeRADIUS");
  });

  it("cancelling closes the dialog without fetching", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasDeviceDeleteButton deviceId={3} deviceName="edge-r1" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByRole("dialog")).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("DELETEs through the BFF and refreshes on confirm", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, status: 204, json: async () => ({}) }),
    );
    render(<NasDeviceDeleteButton deviceId={3} deviceName="edge-r1" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/nas-devices/3");
    expect(init?.method).toBe("DELETE");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("surfaces the backend error and keeps the dialog open", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: "NAS device not found" }),
      }),
    );
    render(<NasDeviceDeleteButton deviceId={999} deviceName="gone" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Delete" }));

    expect((await screen.findByRole("alert")).textContent).toContain("NAS device not found");
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(refreshMock).not.toHaveBeenCalled();
  });

  it("closes on Escape", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasDeviceDeleteButton deviceId={3} deviceName="edge-r1" />);

    fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
