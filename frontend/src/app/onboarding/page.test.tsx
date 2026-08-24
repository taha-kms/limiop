import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import OnboardingPage from "./page";

vi.mock("@/components/onboarding-form", () => ({
  OnboardingForm: () => <p>Onboarding form</p>,
}));

describe("OnboardingPage", () => {
  it("introduces resumable manual onboarding", () => {
    render(<OnboardingPage />);

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "Build your candidate profile",
    );
    expect(screen.getByText(/continue where you stopped/)).toBeVisible();
  });
});
