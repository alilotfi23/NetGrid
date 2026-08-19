import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Plan } from "@/lib/api";
import { PlanForm } from "./plan-form";

const { pushMock, refreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

const PLAN: Plan = {
  id: 7,
  name: "Starter",
  radius_group: "rad_starter",
  price: "9.99",
  duration_days: 30,
  bandwidth_down_mbps: 10,
  bandwidth_up_mbps: 5,
  quota_gb: 100,
  description: null,
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
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Pro" } });
  fireEvent.change(screen.getByLabelText("RADIUS group"), { target: { value: "rad_pro" } });
  fireEvent.change(screen.getByLabelText("Price"), { target: { value: "19.99" } });
}

describe("PlanForm (create)", () => {
  it("renders all inputs", () => {
    render(<PlanForm />);
    expect(screen.getByLabelText("Name")).toBeTruthy();
    expect(screen.getByLabelText("RADIUS group")).toBeTruthy();
    expect(screen.getByLabelText("Price")).toBeTruthy();
    expect(screen.getByLabelText("Duration (days)")).toBeTruthy();
    expect(screen.getByLabelText("Download (Mbps)")).toBeTruthy();
    expect(screen.getByLabelText("Upload (Mbps)")).toBeTruthy();
    expect(screen.getByLabelText("Quota (GB, optional)")).toBeTruthy();
  });

  it("POSTs the payload and navigates to the list on success", async () => {
    mockFetchOnce({ ok: true, status: 201, json: async () => ({ id: 8 }) });
    render(<PlanForm />);
    await fillCreateForm();

    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/plans"));
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(
      expect.objectContaining({
        name: "Pro",
        radius_group: "rad_pro",
        price: "19.99",
        quota_gb: null,
        is_active: true,
      }),
    );
  });

  it("shows the backend error and stays on the form", async () => {
    mockFetchOnce({
      ok: false,
      status: 409,
      json: async () => ({ error: "Plan name or radius group already exists" }),
    });
    render(<PlanForm />);
    await fillCreateForm();

    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Plan name or radius group already exists",
    );
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("validates required fields before submitting", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<PlanForm />);
    fireEvent.click(screen.getByRole("button", { name: "Create plan" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Name is required");
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("PlanForm (edit)", () => {
  it("prefills values and hides immutable fields", () => {
    render(<PlanForm plan={PLAN} />);

    expect(screen.getByLabelText("Price")).toHaveProperty("value", "9.99");
    expect(screen.getByLabelText("Duration (days)")).toHaveProperty("value", "30");
    expect(screen.getByLabelText("Download (Mbps)")).toHaveProperty("value", "10");
    expect(screen.queryByLabelText("Name")).toBeNull();
    expect(screen.queryByLabelText("RADIUS group")).toBeNull();
  });

  it("PATCHes to the plan endpoint and navigates on success", async () => {
    mockFetchOnce({ ok: true, json: async () => ({ ...PLAN, price: "12.50" }) });
    render(<PlanForm plan={PLAN} />);

    fireEvent.change(screen.getByLabelText("Price"), { target: { value: "12.50" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/plans"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/plans/7");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual(expect.objectContaining({ price: "12.50" }));
  });
});
