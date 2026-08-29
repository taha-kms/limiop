import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import RegisterPage from "../register/page";
import SignInPage from "./page";

const currentAccount = vi.hoisted(() => vi.fn());
const redirect = vi.hoisted(() =>
  vi.fn((to: string) => {
    throw new Error(`REDIRECT:${to}`);
  }),
);

vi.mock("@/lib/api/session", () => ({ currentAccount }));
vi.mock("next/navigation", () => ({ redirect }));
vi.mock("@/components/credentials-form", () => ({
  CredentialsForm: ({ mode, next }: { mode: string; next: string }) => (
    <p>
      form:{mode}:{next}
    </p>
  ),
}));

function searchParams(next?: string) {
  return { searchParams: Promise.resolve(next === undefined ? {} : { next }) };
}

describe("the account pages", () => {
  beforeEach(() => {
    currentAccount.mockReset().mockResolvedValue(null);
    redirect.mockClear();
  });

  it("signs a visitor in and returns them to where they were going", async () => {
    render(await SignInPage(searchParams("/onboarding") as never));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Sign in");
    expect(screen.getByText("form:sign-in:/onboarding")).toBeVisible();
  });

  it("carries the destination on to registration, so it survives changing your mind", async () => {
    render(await SignInPage(searchParams("/onboarding") as never));

    expect(screen.getByRole("link", { name: "Create one" })).toHaveAttribute(
      "href",
      "/register?next=%2Fonboarding",
    );
  });

  it("refuses a destination that could leave this site", async () => {
    render(await SignInPage(searchParams("//evil.example") as never));

    expect(screen.getByText("form:sign-in:/")).toBeVisible();
  });

  it("sends someone already signed in on rather than offering a second account", async () => {
    currentAccount.mockResolvedValue({ id: "u1", email: "a@b.example" });

    await expect(SignInPage(searchParams("/onboarding") as never)).rejects.toThrow(
      "REDIRECT:/onboarding",
    );
  });

  it("registers, and says the catalogue does not need an account", async () => {
    render(await RegisterPage(searchParams() as never));

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Create an account");
    expect(screen.getByText("form:register:/")).toBeVisible();
    expect(screen.getByText(/catalogue stays public/)).toBeVisible();
  });

  it("does not offer registration to someone already signed in", async () => {
    currentAccount.mockResolvedValue({ id: "u1", email: "a@b.example" });

    await expect(RegisterPage(searchParams("/jobs") as never)).rejects.toThrow("REDIRECT:/jobs");
  });
});
