import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Admin, Role } from "@/lib/api";
import { AdminForm } from "./admin-form";

const { pushMock, refreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

const ROLES: Role[] = [
  {
    id: 3,
    name: "super_admin",
    description: "Full access",
    permissions: [],
  },
  {
    id: 6,
    name: "support_agent",
    description: "Customer support",
    permissions: [],
  },
];

const ADMIN: Admin = {
  id: 2,
  username: "superadmin",
  email: "superadmin@netgrid.local",
  is_active: true,
  roles: [{ id: 3, name: "super_admin", description: null }],
};

function mockFetchOnce(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
  pushMock.mockClear();
  refreshMock.mockClear();
});

describe("AdminForm (create)", () => {
  it("POSTs the payload with selected role ids and navigates", async () => {
    mockFetchOnce({ ok: true, status: 201, json: async () => ({ id: 9 }) });
    render(<AdminForm roles={ROLES} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "bob" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "bob@netgrid.local" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "secret123" } });
    fireEvent.click(screen.getByRole("checkbox", { name: /support_agent/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create admin" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admins"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/admins");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      username: "bob",
      email: "bob@netgrid.local",
      password: "secret123",
      is_active: true,
      role_ids: [6],
    });
  });

  it("validates password length before submitting", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<AdminForm roles={ROLES} />);

    fireEvent.change(screen.getByLabelText("Username"), { target: { value: "bob" } });
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "bob@netgrid.local" } });
    fireEvent.change(screen.getByLabelText("Password"), { target: { value: "short" } });
    fireEvent.click(screen.getByRole("button", { name: "Create admin" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Password must be at least 8 characters",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("AdminForm (edit)", () => {
  it("PATCHes the profile then PUTs the role set", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ADMIN })
        .mockResolvedValueOnce({ ok: true, json: async () => ADMIN }),
    );
    render(<AdminForm admin={ADMIN} roles={ROLES} />);

    expect(screen.getByLabelText("Username")).toHaveProperty("value", "superadmin");
    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@netgrid.local" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admins"));
    const calls = vi.mocked(fetch).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][0]).toBe("/api/admins/2");
    expect(calls[0][1]?.method).toBe("PATCH");
    expect(JSON.parse(String(calls[0][1]?.body))).toEqual({
      username: "superadmin",
      email: "new@netgrid.local",
      is_active: true,
    });
    expect(calls[1][0]).toBe("/api/admins/2/roles");
    expect(calls[1][1]?.method).toBe("PUT");
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({ role_ids: [3] });
  });

  it("hides the role picker for self and skips the roles PUT", async () => {
    mockFetchOnce({ ok: true, json: async () => ADMIN });
    render(<AdminForm admin={ADMIN} roles={ROLES} isSelf />);

    expect(screen.queryByRole("checkbox", { name: /super_admin/ })).toBeNull();
    expect(screen.getByText(/self-protection/)).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Email"), { target: { value: "new@netgrid.local" } });
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/admins"));
    expect(vi.mocked(fetch).mock.calls).toHaveLength(1);
    expect(vi.mocked(fetch).mock.calls[0][0]).toBe("/api/admins/2");
  });

  it("surfaces the backend error and stays on the form", async () => {
    mockFetchOnce({
      ok: false,
      status: 400,
      json: async () => ({ error: "Cannot deactivate yourself" }),
    });
    render(<AdminForm admin={ADMIN} roles={ROLES} isSelf />);

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Cannot deactivate yourself",
    );
    expect(pushMock).not.toHaveBeenCalled();
  });
});
