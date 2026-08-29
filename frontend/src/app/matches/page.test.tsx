import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { JobMatch } from "@/lib/api/matches";
import { MatchesUnavailableError, NotSignedInError } from "@/lib/api/matches";

import MatchesPage from "./page";

const getMatches = vi.hoisted(() => vi.fn());
const redirect = vi.hoisted(() =>
  vi.fn((to: string) => {
    throw new Error(`REDIRECT:${to}`);
  }),
);

vi.mock("@/lib/api/matches", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api/matches")>()),
  getMatches,
}));
vi.mock("next/navigation", () => ({ redirect }));

function match(overrides: Partial<JobMatch> = {}): JobMatch {
  return {
    job: {
      id: "job-1",
      company: { id: "c1", display_name: "Acme GmbH" },
      title: "Backend Engineer",
      excerpt: "Work.",
      location: "Berlin",
      workplace_type: "remote",
      employment_type: "full-time",
      application_url: "https://acme.example.com/apply",
      published_at: null,
    },
    score: 0.75,
    matched_skills: [{ concept_id: "s1", preferred_label: "Python" }],
    missing_skills: [{ concept_id: "s2", preferred_label: "SQL" }],
    ...overrides,
  } as JobMatch;
}

describe("MatchesPage", () => {
  beforeEach(() => {
    getMatches.mockReset();
    redirect.mockClear();
  });

  it("shows a ranked job with both halves of the reason", async () => {
    getMatches.mockResolvedValue({ matches: [match()], ranked: 1 });

    render(await MatchesPage());

    expect(screen.getByRole("link", { name: "Backend Engineer" })).toBeVisible();
    expect(screen.getByText("1 of 2 skills")).toBeVisible();
    expect(screen.getByText("You have")).toBeVisible();
    expect(screen.getByText("Python")).toBeVisible();
    expect(screen.getByText("This role also asks for")).toBeVisible();
    expect(screen.getByText("SQL")).toBeVisible();
  });

  it("keeps applying a link to the employer", async () => {
    getMatches.mockResolvedValue({ matches: [match()], ranked: 1 });

    render(await MatchesPage());

    expect(screen.getByRole("link", { name: /Apply on the employer/ })).toHaveAttribute(
      "href",
      "https://acme.example.com/apply",
    );
  });

  it("says how many were ranked, so a short page is not a small catalogue", async () => {
    getMatches.mockResolvedValue({ matches: [match()], ranked: 42 });

    render(await MatchesPage());

    expect(screen.getByText(/Ranked 42 jobs/)).toBeVisible();
  });

  it("tells an empty result what to do next rather than what happened", async () => {
    getMatches.mockResolvedValue({ matches: [], ranked: 0 });

    render(await MatchesPage());

    expect(screen.getByRole("heading", { name: "No matches yet" })).toBeVisible();
    expect(screen.getByRole("link", { name: /Add some to your profile/ })).toHaveAttribute(
      "href",
      "/onboarding",
    );
  });

  it("sends an anonymous visitor to sign in and back again", async () => {
    getMatches.mockRejectedValue(new NotSignedInError());

    await expect(MatchesPage()).rejects.toThrow("REDIRECT:/sign-in?next=%2Fmatches");
  });

  it("says matches could not be loaded rather than rendering an empty ranking", async () => {
    getMatches.mockRejectedValue(new MatchesUnavailableError());

    render(await MatchesPage());

    expect(screen.getByRole("heading", { name: "Matches could not be loaded" })).toBeVisible();
    expect(screen.queryByRole("heading", { name: "No matches yet" })).toBeNull();
  });

  it("hides a skill list that would be empty", async () => {
    getMatches.mockResolvedValue({
      matches: [match({ score: 1, missing_skills: [] })],
      ranked: 1,
    });

    render(await MatchesPage());

    expect(screen.getByText("You have")).toBeVisible();
    expect(screen.queryByText("This role also asks for")).toBeNull();
  });
});
