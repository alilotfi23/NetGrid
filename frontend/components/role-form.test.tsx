import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Permission, Role } from "@/lib/api";
import { RoleForm } from "./role-form";

const { pushMock, refreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

const PERMISSIONS: Permission[] = [
  { id: 14, code: "subscribers:read", description: null },
  { id: 15, code: "subscribers:write", description: null },
  { id: 19, code: "invoices:read", description: null },
  { id: 29, code: "*:*", description: "Full access" },
];

const ROLE: Role = {
  id: 6,
  name: "support_agent",
  description: "Customer support",
  permissions: [PERMISSIONS[0], PERMISSIONS[2]],
};

function mockFetchOnce(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
  pushMock.mockClear();
  refreshMock.mockClear();
});

describe("RoleForm (create)", () => {
  it("groups permissions by resource and POSTs the selected codes", async () => {
    mockFetchOnce({ ok: true, status: 201, json: async () => ROLE });
    render(<RoleForm permissions={PERMISSIONS} />);

    // groups render with their resource headers
    expect(screen.getByText("Wildcard")).toBeTruthy();
    expect(screen.getByText("subscribers")).toBeTruthy();
    expect(screen.getByText("invoices")).toBeTruthy();

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "support_agent" } });
    fireEvent.change(screen.getByLabelText("Description (optional)"), {
      target: { value: "Customer support" },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: "subscribers:read" }));
    fireEvent.click(screen.getByRole("button", { name: "Create role" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/roles"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/roles");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      name: "support_agent",
      description: "Customer support",
      permission_codes: ["subscribers:read"],
    });
  });

  it("validates the name before submitting", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<RoleForm permissions={PERMISSIONS} />);

    fireEvent.click(screen.getByRole("button", { name: "Create role" }));

    expect((await screen.findByRole("alert")).textContent).toContain("Name is required");
    expect(fetch).not.toHaveBeenCalled();
  });
});

describe("RoleForm (edit)", () => {
  it("prefills the current permission set", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<RoleForm role={ROLE} permissions={PERMISSIONS} />);

    expect(screen.getByLabelText("Name")).toHaveProperty("value", "support_agent");
    const read = screen.getByRole("checkbox", { name: "subscribers:read" });
    expect(read).toHaveProperty("checked", true);
  });

  it("PATCHes the profile then PUTs the permission set", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ROLE })
        .mockResolvedValueOnce({ ok: true, json: async () => ROLE }),
    );
    render(<RoleForm role={ROLE} permissions={PERMISSIONS} />);

    // add subscribers:write to the existing set
    fireEvent.click(screen.getByRole("checkbox", { name: "subscribers:write" }));
    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/roles"));
    const calls = vi.mocked(fetch).mock.calls;
    expect(calls).toHaveLength(2);
    expect(calls[0][0]).toBe("/api/roles/6");
    expect(calls[0][1]?.method).toBe("PATCH");
    expect(calls[1][0]).toBe("/api/roles/6/permissions");
    expect(calls[1][1]?.method).toBe("PUT");
    expect(JSON.parse(String(calls[1][1]?.body))).toEqual({
      permission_codes: ["subscribers:read", "invoices:read", "subscribers:write"],
    });
  });

  it("surfaces the self-protection error from the backend", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValueOnce({ ok: true, json: async () => ROLE })
        .mockResolvedValueOnce({
          ok: false,
          status: 400,
          json: async () => ({ error: "This change would remove your own admins:manage access" }),
        }),
    );
    render(<RoleForm role={ROLE} permissions={PERMISSIONS} />);

    fireEvent.click(screen.getByRole("button", { name: "Save changes" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "This change would remove your own admins:manage access",
    );
    expect(pushMock).not.toHaveBeenCalled();
  });
});
