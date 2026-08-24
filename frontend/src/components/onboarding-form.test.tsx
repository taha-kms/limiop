import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { CandidateProfile } from "@/lib/api/profile";

import { OnboardingForm } from "./onboarding-form";

function profile(overrides: Partial<CandidateProfile> = {}): CandidateProfile {
  return {
    id: "00000000-0000-0000-0000-000000000001",
    display_name: null,
    location: null,
    workplace_types: null,
    employment_types: null,
    headline: null,
    summary: null,
    years_experience: null,
    profile_complete: false,
    created_at: "2026-08-24T00:00:00Z",
    updated_at: "2026-08-24T00:00:00Z",
    ...overrides,
  };
}

function response(body: object, status = 200): Response {
  return Response.json(body, { status });
}

afterEach(() => vi.unstubAllGlobals());

describe("OnboardingForm", () => {
  it("saves each canonical field and advances one step", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response({}, 404))
      .mockResolvedValueOnce(response(profile({ display_name: "Ada" })))
      .mockResolvedValueOnce(response(profile({ display_name: "Ada", location: "London" })));
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();

    render(<OnboardingForm />);
    await user.type(await screen.findByLabelText("What should employers call you?"), "Ada");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));
    await user.type(await screen.findByLabelText("Where are you based?"), "London");
    await user.click(screen.getByRole("button", { name: "Save and continue" }));

    expect(await screen.findByText("Step 3 of 3")).toBeVisible();
    expect(fetch).toHaveBeenNthCalledWith(
      2,
      "/api/profile",
      expect.objectContaining({ body: JSON.stringify({ display_name: "Ada" }) }),
    );
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/api/profile",
      expect.objectContaining({ body: JSON.stringify({ location: "London" }) }),
    );
  });

  it("resumes from the first required field that is still absent", async () => {
    vi.stubGlobal(
      "fetch",
      vi
        .fn()
        .mockResolvedValue(
          response(profile({ display_name: "Ada", location: "London", profile_complete: false })),
        ),
    );

    render(<OnboardingForm />);

    expect(await screen.findByText("Step 3 of 3")).toBeVisible();
    expect(screen.queryByLabelText("What should employers call you?")).not.toBeInTheDocument();
  });

  it("requires controlled preferences before completing the profile", async () => {
    const complete = profile({
      display_name: "Ada",
      location: "London",
      workplace_types: ["hybrid"],
      employment_types: ["full-time"],
      profile_complete: true,
    });
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(
        response(profile({ display_name: "Ada", location: "London", profile_complete: false })),
      )
      .mockResolvedValueOnce(response(complete));
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();
    render(<OnboardingForm />);

    await user.click(await screen.findByRole("button", { name: "Complete profile" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/Choose at least one workplace/);

    await user.click(screen.getByRole("checkbox", { name: "Hybrid" }));
    await user.click(screen.getByRole("checkbox", { name: "Full-time" }));
    await user.click(screen.getByRole("button", { name: "Complete profile" }));

    expect(await screen.findByRole("heading", { name: "Your profile is ready" })).toBeVisible();
  });

  it("explains that authentication is required", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response({}, 401)));

    render(<OnboardingForm />);

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/Sign in/));
  });
});
