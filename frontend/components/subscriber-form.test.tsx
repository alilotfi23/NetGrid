import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Plan, Subscriber } from "@/lib/api";
import { SubscriberForm } from "./subscriber-form";

const { pushMock, refreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

const PLANS: Plan[] = [
  {
    id: 1,
    name: "Starter",
    radius_group: "rad_starter",
    price: "9.99",
    duration_days: 30,
    bandwidth_down_mbps: 10,
    bandwidth_up_mbps: 5,
    quota_gb: 100,
    description: null,
    is_active: true,
    enforce_quota: false,
    created_at: "2026-08-19T00:00:00",
    subscriber_count: 2,
  },
  {
    id: 2,
    name: "Pro",
    radius_group: "rad_pro",
    price: "19.99",
    duration_days: 30,
    bandwidth_down_mbps: 50,
    bandwidth_up_mbps: 25,
    quota_gb: 500,
    description: null,
    is_active: true,
    enforce_quota: false,
    created_at: "2026-08-19T00:00:00",
    subscriber_count: 0,
  },
];

const SUBSCRIBER: Subscriber = {
  id: 7,
  username: "bob",
  full_name: "Bob Subscriber",
  email: "bob@netgrid.local",
  phone: null,
  status: "active",
  plan_id: 1,
  notes: null,
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

describe("SubscriberForm (create)", () => {
  it("renders all inputs including the plan select", () => {
    render(<SubscriberForm plans={PLANS} />);
    expect(screen.getByLabelText("Username")).toBeTruthy();
    expect(screen.getByLabelText("Password")).toBeTruthy();
    expect(screen.getByLabelText("Full name")).toBeTruthy();
    expect(screen.getByLabelText("Status")).toBeTruthy();
    const planSelect = screen.getByLabelText("Plan") as HTMLSelectElement;
    expect(planSelect.options.length).toBe(3); // No plan + 2 plans
    expect(planSelect.options[2].textContent).toBe("Pro");
  });

  it("POSTs the payload with plan assignment and navigates to the profile", async () => {
    mockFetchOnce({ ok: true, status: 201, json: async () => ({ id: 9 }) });
    render(<SubscriberForm plans={PLANS} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "carol" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "radpass123" } });
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Carol Subscriber" } });
    fireEvent.change(screen.getByLabelText("Plan"), { target: { value: "2" } });
    fireEvent.click(screen.getByRole("button", { name: "Create subscriber" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/subscribers/9"));
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual(
      expect.objectContaining({
        username: "carol",
        full_name: "Carol Subscriber",
        password: "radpass123",
        status: "active",
        plan_id: 2,
        email: null,
        phone: null,
        notes: null,
      }),
    );
  });

  it("validates required fields before submitting", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<SubscriberForm plans={PLANS} />);
    fireEvent.click(screen.getByRole("button", { name: "Create subscriber" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Full name is required");
    expect(fetch).not.toHaveBeenCalled();
  });

  it("shows the backend error and stays on the form", async () => {
    mockFetchOnce({
      ok: false,
      status: 409,
      json: async () => ({ error: "Username already exists" }),
    });
    render(<SubscriberForm plans={PLANS} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "bob" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "radpass123" } });
    fireEvent.change(screen.getByLabelText("Full name"), { target: { value: "Bob Again" } });
    fireEvent.click(screen.getByRole("button", { name: "Create subscriber" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Username already exists");
    expect(pushMock).not.toHaveBeenCalled();
  });
});

describe("SubscriberForm (edit)", () => {
  it("prefills values and hides immutable fields", () => {
    render(<SubscriberForm subscriber={SUBSCRIBER} plans={PLANS} />);

    expect(screen.getByLabelText("Full name")).toHaveProperty("value", "Bob Subscriber");
    expect(screen.getByLabelText("Status")).toHaveProperty("value", "active");
    expect((screen.getByLabelText("Plan") as HTMLSelectElement).value).toBe("1");
    expect(screen.queryByLabelText("Username")).toBeNull();
    expect(screen.queryByLabelText("Password")).toBeNull();
  });

  it("PATCHes status changes and navigates back to the profile", async () => {
    mockFetchOnce({ ok: true, json: async () => ({ ...SUBSCRIBER, status: "suspended" }) });
    render(<SubscriberForm subscriber={SUBSCRIBER} plans={PLANS} />);

    fireEvent.change(screen.getByLabelText("Status"), { target: { value: "suspended" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/subscribers/7"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/subscribers/7");
    expect(init?.method).toBe("PATCH");
    expect(JSON.parse(String(init?.body))).toEqual(
      expect.objectContaining({ status: "suspended", plan_id: 1 }),
    );
  });

  it("allows clearing the plan", async () => {
    mockFetchOnce({ ok: true, json: async () => ({ ...SUBSCRIBER, plan_id: null }) });
    render(<SubscriberForm subscriber={SUBSCRIBER} plans={PLANS} />);

    fireEvent.change(screen.getByLabelText("Plan"), { target: { value: "" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/subscribers/7"));
    const [, init] = vi.mocked(fetch).mock.calls[0];
    expect(JSON.parse(String(init?.body))).toEqual(expect.objectContaining({ plan_id: null }));
  });
});
