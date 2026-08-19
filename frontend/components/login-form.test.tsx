import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { LoginForm } from "./login-form";

const { pushMock, refreshMock } = vi.hoisted(() => ({
  pushMock: vi.fn(),
  refreshMock: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: pushMock, refresh: refreshMock }),
}));

function mockFetchOnce(response: Partial<Response>): void {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response));
}

afterEach(() => {
  vi.unstubAllGlobals();
  pushMock.mockClear();
  refreshMock.mockClear();
});

async function fillForm(username = "superadmin", password = "netgrid-admin") {
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
}

describe("LoginForm", () => {
  it("POSTs credentials to the BFF and navigates to the dashboard on success", async () => {
    mockFetchOnce({ ok: true, status: 200, json: async () => ({ admin: { username: "superadmin" } }) });
    render(<LoginForm />);
    await fillForm();

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    await waitFor(() => expect(pushMock).toHaveBeenCalledWith("/"));
    const [url, init] = vi.mocked(fetch).mock.calls[0];
    expect(url).toBe("/api/auth/login");
    expect(init?.method).toBe("POST");
    expect(JSON.parse(String(init?.body))).toEqual({
      username: "superadmin",
      password: "netgrid-admin",
    });
  });

  it("shows the backend error on invalid credentials and stays put", async () => {
    mockFetchOnce({
      ok: false,
      status: 401,
      json: async () => ({ error: "Invalid username or password" }),
    });
    render(<LoginForm />);
    await fillForm("superadmin", "wrongpass");

    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Invalid username or password",
    );
    expect(pushMock).not.toHaveBeenCalled();
  });

  it("validates required fields before submitting", async () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<LoginForm />);
    fireEvent.click(screen.getByRole("button", { name: "Sign in" }));

    expect((await screen.findByRole("alert")).textContent).toContain(
      "Username and password are required",
    );
    expect(fetch).not.toHaveBeenCalled();
  });
});
