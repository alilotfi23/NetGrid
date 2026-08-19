import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { NasDeviceStatusButton } from "./nas-device-status-button";

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

describe("NasDeviceStatusButton", () => {
  it("shows Deactivate for an active device and PATCHes is_active=false", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    render(<NasDeviceStatusButton deviceId={3} isActive={true} />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/nas-devices/3");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual({ is_active: false });
  });

  it("shows Activate for an inactive device and PATCHes is_active=true", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) }));
    render(<NasDeviceStatusButton deviceId={3} isActive={false} />);

    fireEvent.click(screen.getByRole("button", { name: "Activate" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual({ is_active: true });
  });

  it("surfaces the backend error without refreshing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ error: "NAS device name or IP address already exists" }),
      }),
    );
    render(<NasDeviceStatusButton deviceId={3} isActive={true} />);

    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));

    expect(await screen.findByText(/already exists/)).toBeTruthy();
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
