import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import OnboardingPage from "./page";

const currentAccount = vi.hoisted(() => vi.fn());
const redirect = vi.hoisted(() =>
  vi.fn((to: string) => {
    throw new Error(`REDIRECT:${to}`);
  }),
);

vi.mock("@/components/onboarding-form", () => ({
  OnboardingForm: () => <p>Onboarding form</p>,
}));
vi.mock("@/lib/api/session", () => ({ currentAccount }));
vi.mock("next/navigation", () => ({ redirect }));

describe("OnboardingPage", () => {
  beforeEach(() => {
    currentAccount.mockReset();
    redirect.mockClear();
  });

  it("introduces resumable manual onboarding", async () => {
    currentAccount.mockResolvedValue({ id: "u1", email: "candidate@example.com" });

    render(await OnboardingPage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Build your candidate profile",
    );
    expect(screen.getByText(/continue where you stopped/)).toBeVisible();
  });

  it("sends an anonymous visitor to sign in rather than to a form that will be refused", async () => {
    currentAccount.mockResolvedValue(null);

    await expect(OnboardingPage()).rejects.toThrow("REDIRECT:/sign-in?next=%2Fonboarding");
    expect(redirect).toHaveBeenCalledWith("/sign-in?next=%2Fonboarding");
  });
});
