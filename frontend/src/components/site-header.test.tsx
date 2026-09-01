import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SiteHeader } from "./site-header";

const currentAccount = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/session", () => ({ currentAccount }));
vi.mock("./sign-out-button", () => ({ SignOutButton: () => <button>Sign out</button> }));

describe("SiteHeader", () => {
  beforeEach(() => currentAccount.mockReset());

  it("offers an anonymous visitor a way in, and never a profile link", async () => {
    currentAccount.mockResolvedValue(null);

    render(await SiteHeader());

    expect(screen.getByRole("link", { name: "Sign in" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Create an account" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Your profile" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Account" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Matches" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Sign out" })).toBeNull();
  });

  it("keeps the catalogue reachable whether or not anyone is signed in", async () => {
    currentAccount.mockResolvedValue(null);
    const { unmount } = render(await SiteHeader());
    expect(screen.getByRole("link", { name: "Jobs" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Job market" })).toBeVisible();
    unmount();

    currentAccount.mockResolvedValue({ id: "u1", email: "candidate@example.com" });
    render(await SiteHeader());
    expect(screen.getByRole("link", { name: "Jobs" })).toBeVisible();
  });

  it("names who is signed in and offers the way out", async () => {
    currentAccount.mockResolvedValue({ id: "u1", email: "candidate@example.com" });

    render(await SiteHeader());

    expect(screen.getByText("candidate@example.com")).toBeVisible();
    expect(screen.getByRole("link", { name: "Matches" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Your CV" })).toBeVisible();
    expect(screen.getByRole("link", { name: "Your profile" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign out" })).toBeVisible();
    expect(screen.queryByRole("link", { name: "Sign in" })).toBeNull();
  });

  it("reaches the account page, which is the only way in to what it holds", async () => {
    currentAccount.mockResolvedValue({ id: "u1", email: "candidate@example.com" });

    render(await SiteHeader());

    expect(screen.getByRole("link", { name: "Account" })).toHaveAttribute("href", "/account");
  });
});
