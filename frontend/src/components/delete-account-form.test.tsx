import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DeleteAccountForm } from "./delete-account-form";

const replace = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  Object.defineProperty(window, "location", { configurable: true, value: { replace } });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function confirmWith(password: string) {
  await userEvent.click(screen.getByRole("button", { name: "Delete account" }));
  if (password) await userEvent.type(screen.getByLabelText("Confirm your password"), password);
  await userEvent.click(screen.getByRole("button", { name: /Delete my account/ }));
}

describe("DeleteAccountForm", () => {
  it("asks for the password before it asks the API for anything", async () => {
    render(<DeleteAccountForm />);

    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));

    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Confirm your password")).toBeVisible();
  });

  it("sends the password and leaves for a page an account is not needed for", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    render(<DeleteAccountForm />);

    await confirmWith("correct horse battery staple");

    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/account",
      expect.objectContaining({ method: "DELETE", credentials: "same-origin" }),
    );
    expect(JSON.parse(vi.mocked(fetch).mock.calls[0][1]?.body as string)).toEqual({
      password: "correct horse battery staple",
    });
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("says which password was refused rather than that something broke", async () => {
    vi.mocked(fetch).mockResolvedValue(Response.json({ detail: "no" }, { status: 403 }));
    render(<DeleteAccountForm />);

    await confirmWith("wrong");

    expect(screen.getByRole("alert")).toHaveTextContent("password was not accepted");
    expect(replace).not.toHaveBeenCalled();
  });

  it("refuses an empty confirmation without asking the API", async () => {
    render(<DeleteAccountForm />);

    await confirmWith("");

    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByRole("alert")).toHaveTextContent("Enter your password");
  });

  it("lets the reader keep their account", async () => {
    render(<DeleteAccountForm />);

    await userEvent.click(screen.getByRole("button", { name: "Delete account" }));
    await userEvent.click(screen.getByRole("button", { name: "Keep my account" }));

    expect(screen.getByRole("button", { name: "Delete account" })).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("keeps the form usable when the service cannot be reached", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("network"));
    render(<DeleteAccountForm />);

    await confirmWith("correct horse battery staple");

    expect(screen.getByRole("alert")).toBeVisible();
    expect(screen.getByRole("button", { name: /Delete my account/ })).toBeEnabled();
  });
});
