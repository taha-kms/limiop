import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import AccountPage from "./page";

const currentAccount = vi.hoisted(() => vi.fn());
const redirect = vi.hoisted(() =>
  vi.fn((to: string) => {
    throw new Error(`REDIRECT:${to}`);
  }),
);

vi.mock("@/components/change-password-form", () => ({
  ChangePasswordForm: () => <p>Change password</p>,
}));
vi.mock("@/components/sign-out-everywhere-button", () => ({
  SignOutEverywhereButton: () => <p>Sign out everywhere</p>,
}));
vi.mock("@/components/delete-account-form", () => ({
  DeleteAccountForm: () => <p>Delete your account</p>,
}));
vi.mock("@/lib/api/session", () => ({ currentAccount }));
vi.mock("next/navigation", () => ({ redirect }));

describe("AccountPage", () => {
  beforeEach(() => {
    currentAccount.mockReset();
    redirect.mockClear();
  });

  it("gathers everything that is about the account rather than the candidate", async () => {
    currentAccount.mockResolvedValue({ id: "u1", email: "candidate@example.com" });

    render(await AccountPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Your account");
    expect(screen.getByText("Change password")).toBeVisible();
    expect(screen.getByText("Sign out everywhere")).toBeVisible();
    expect(screen.getByText("Delete your account")).toBeVisible();
  });

  it("names the account being acted on, since all three actions are irreversible-ish", async () => {
    currentAccount.mockResolvedValue({ id: "u1", email: "candidate@example.com" });

    render(await AccountPage());

    expect(screen.getByText("candidate@example.com")).toBeVisible();
  });

  it("sends an anonymous visitor to sign in rather than to forms that will be refused", async () => {
    currentAccount.mockResolvedValue(null);

    await expect(AccountPage()).rejects.toThrow("REDIRECT:/sign-in?next=%2Faccount");
    expect(redirect).toHaveBeenCalledWith("/sign-in?next=%2Faccount");
  });
});
