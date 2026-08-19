import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { NasDevice } from "@/lib/api";
import { NasDeviceForm } from "./nas-device-form";

const { pushMock, refreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

const DEVICE: NasDevice = {
  id: 3,
  name: "edge-r1",
  ip_address: "192.168.0.10",
  shortname: "edge1",
  nas_type: "cisco",
  ports: 1812,
  server: null,
  community: null,
  description: "core router",
  is_active: true,
  created_at: "2026-08-19T00:00:00",
};

function mockFetchOnce(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
  pushMock.mockClear();
  refreshMock.mockClear();
});

async function fillCreateForm() {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "edge-r2" } });
  fireEvent.change(screen.getByLabelText("IP address"), { target: { value: "10.0.0.1" } });
  fireEvent.change(screen.getByLabelText("Shortname"), { target: { value: "edge2" } });
  fireEvent.change(screen.getByLabelText("Shared secret"), { target: { value: "sekrit123" } });
  fireEvent.change(screen.getByLabelText("Ports (optional)"), { target: { value: "1812" } });
}

describe("NasDeviceForm (create)", () => {
  it("renders all inputs including the secret", () => {
    render(<NasDeviceForm />);
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect(screen.getByLabelText("IP address")).toBeTruthy();
    expect(screen.getByLabelText("Shortname")).toBeTruthy();
    expect(screen.getByLabelText("NAS type")).toBeTruthy();
    expect(screen.getByLabelText("Shared secret")).toBeTruthy();
    expect(screen.getByLabelText("Ports (optional)")).toBeTruthy();
    expect(screen.getByLabelText("Server (optional)")).toBeTruthy();
    expect(screen.getByLabelText("Community (optional)")).toBeTruthy();
  });

  it("POSTs the payload with the secret and navigates on success", async () => {
    mockFetchOnce({ ok: true, status: 201, json: async () => ({ id: 9 }) });
    render(<NasDeviceForm />);
    await fillCreateForm();

    fireEvent.click(screen.getByRole("button", { name: "Create NAS device" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/nas-devices"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/nas-devices");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(
      expect.objectContaining({
        name: "edge-r2",
        ip_address: "10.0.0.1",
        shortname: "edge2",
        nas_type: "other",
        secret: "sekrit123",
        ports: 1812,
        is_active: true,
      }),
    );
  });

  it("shows the backend error and stays on the form", async () => {
    mockFetchOnce({
      ok: false,
      status: 409,
      json: async () => ({ error: "NAS device name or IP address already exists" }),
    });
    render(<NasDeviceForm />);
    await fillCreateForm();

    fireEvent.click(screen.getByRole("button", { name: "Create NAS device" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "NAS device name or IP address already exists",
    );
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("validates required fields before submitting", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasDeviceForm />);
    fireEvent.click(screen.getByRole("button", { name: "Create NAS device" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Name and shortname are required",
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires the shared secret on create", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<NasDeviceForm />);
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "edge-r2" } });
    fireEvent.change(screen.getByLabelText("IP address"), { target: { value: "10.0.0.1" } });
    fireEvent.change(screen.getByLabelText("Shortname"), { target: { value: "edge2" } });
    fireEvent.click(screen.getByRole("button", { name: "Create NAS device" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Shared secret is required",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("NasDeviceForm (edit)", () => {
  it("prefills values and hides the immutable IP field and the secret field", () => {
    render(<NasDeviceForm device={DEVICE} />);

    expect(screen.getByLabelText("Name")).toHaveProperty("value", "edge-r1");
    expect(screen.getByLabelText("Shortname")).toHaveProperty("value", "edge1");
    expect(screen.getByLabelText("NAS type")).toHaveProperty("value", "cisco");
    expect(screen.getByLabelText("Ports (optional)")).toHaveProperty("value", "1812");
    const ip = screen.getByLabelText("IP address") as HTMLInputElement;
    expect(ip).toHaveProperty("value", "192.168.0.10");
    expect(ip).toHaveProperty("disabled", true);
    // rotation lives on the dedicated RotateSecretForm, not the edit form
    expect(screen.queryByLabelText(/shared secret/i)).toBeNull();
  });

  it("PATCHes field changes without ever sending a secret", async () => {
    mockFetchOnce({ ok: true, json: async () => ({ ...DEVICE, description: "core" }) });
    render(<NasDeviceForm device={DEVICE} />);

    fireEvent.change(screen.getByLabelText("Description (optional)"), {
      target: { value: "core" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/nas-devices"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/nas-devices/3");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual(
      expect.not.objectContaining({ secret: expect.anything() }),
    );
  });

  it("deactivating unchecks the active box and sends is_active=false", async () => {
    mockFetchOnce({ ok: true, json: async () => ({ ...DEVICE, is_active: false }) });
    render(<NasDeviceForm device={DEVICE} />);

    fireEvent.click(screen.getByLabelText(/Active/));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/nas-devices"));
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual(expect.objectContaining({ is_active: false }));
  });
});
