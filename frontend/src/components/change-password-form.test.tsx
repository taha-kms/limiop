import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChangePasswordForm } from "./change-password-form";

beforeEach(() => vi.stubGlobal("fetch", vi.fn()));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function change(current: string, next: string) {
  if (current) await userEvent.type(screen.getByLabelText("Current password"), current);
  if (next) await userEvent.type(screen.getByLabelText("New password"), next);
  await userEvent.click(screen.getByRole("button", { name: /Change password/ }));
}

describe("ChangePasswordForm", () => {
  it("says what changing the password does to other devices, before it is used", () => {
    render(<ChangePasswordForm />);

    expect(screen.getByText(/Every other device is signed out/)).toBeVisible();
  });

  it("sends both passwords and reports the change", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    render(<ChangePasswordForm />);

    await change("correct horse battery", "a different long password");

    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/password",
      expect.objectContaining({ method: "POST", credentials: "same-origin" }),
    );
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string)).toEqual({
      current_password: "correct horse battery",
      new_password: "a different long password",
    });
    expect(await screen.findByRole("status")).toHaveTextContent(/Password changed/);
  });

  it("stays on the page, because this device keeps its session", async () => {
    const replace = vi.fn();
    Object.defineProperty(window, "location", { configurable: true, value: { replace } });
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    render(<ChangePasswordForm />);

    await change("correct horse battery", "a different long password");

    expect(replace).not.toHaveBeenCalled();
  });

  it("asks for nothing from the API until both fields are filled", async () => {
    render(<ChangePasswordForm />);

    await change("", "");

    expect(fetch).not.toHaveBeenCalled();
    expect(await screen.findByRole("alert")).toHaveTextContent("Fill in both fields.");
  });

  it("reports a refused current password in the reader's terms", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 403 }));
    render(<ChangePasswordForm />);

    await change("not the password", "a different long password");

    expect(await screen.findByRole("alert")).toHaveTextContent(/was not accepted/);
    expect(screen.queryByRole("status")).toBeNull();
  });

  it("reports a password under the floor as the length it is", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 422 }));
    render(<ChangePasswordForm />);

    await change("correct horse battery", "short");

    expect(await screen.findByRole("alert")).toHaveTextContent(/at least 12 characters/);
  });
});
