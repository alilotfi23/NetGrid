import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RotateSecretForm } from "./rotate-secret-form";

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

async function fillSecrets(secret = "new-secret-99") {
  fireEvent.change(screen.getByLabelText("New shared secret"), {
    target: { value: secret },
  });
  fireEvent.change(screen.getByLabelText("Confirm new secret"), {
    target: { value: secret },
  });
}

describe("RotateSecretForm", () => {
  it("POSTs the matching secrets to the rotate endpoint and refreshes", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 3 }) }));
    render(<RotateSecretForm deviceId={3} deviceName="edge-r1" />);

    await fillSecrets();
    fireEvent.click(screen.getByRole("button", { name: "Rotate secret" }));

    await waitFor(() => expect(refreshMock).toHaveBeenCalled());
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/nas-devices/3/rotate-secret");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({ secret: "new-secret-99" });
  });

  it("shows a success message and clears the fields", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ id: 3 }) }));
    render(<RotateSecretForm deviceId={3} deviceName="edge-r1" />);

    await fillSecrets();
    fireEvent.click(screen.getByRole("button", { name: "Rotate secret" }));

    expect((await screen.findByRole("status")).textContent).toContain(
      "Shared secret for edge-r1 rotated",
    );
    expect(screen.getByLabelText("New shared secret")).toHaveProperty("value", "");
  });

  it("rejects mismatched secrets without submitting", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<RotateSecretForm deviceId={3} deviceName="edge-r1" />);

    fireEvent.change(screen.getByLabelText("New shared secret"), {
      target: { value: "secret-a" },
    });
    fireEvent.change(screen.getByLabelText("Confirm new secret"), {
      target: { value: "secret-b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rotate secret" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Secrets do not match");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("requires a non-empty secret", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<RotateSecretForm deviceId={3} deviceName="edge-r1" />);

    fireEvent.click(screen.getByRole("button", { name: "Rotate secret" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "New shared secret is required",
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it("surfaces the backend error without refreshing", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
        status: 422,
        json: async () => ({ error: "Request validation failed" }),
      }),
    );
    render(<RotateSecretForm deviceId={3} deviceName="edge-r1" />);

    await fillSecrets();
    fireEvent.click(screen.getByRole("button", { name: "Rotate secret" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Request validation failed",
    );
    expect(refreshMock).not.toHaveBeenCalled();
  });
});
