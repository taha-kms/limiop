import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import type { JobSummary } from "@/lib/api/types";

import HomePage from "./page";

const currentAccount = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/session", () => ({ currentAccount }));

const JOB: JobSummary = {
  id: "job-1",
  company: { id: "c1", display_name: "Meridian Software", website_url: null },
  title: "Remote Data Engineer",
  excerpt: "Build the pipelines.",
  location: "Berlin",
  workplace_type: "remote",
  employment_type: "full-time",
  application_url: "https://example.com/apply",
  published_at: "2026-01-03T00:00:00Z",
};

function catalogue(items: JobSummary[]) {
  return { items, next_cursor: null };
}

describe("HomePage", () => {
  beforeEach(() => currentAccount.mockResolvedValue(null));
  afterEach(() => vi.restoreAllMocks());

  it("leads with what the product does and offers both ways in", async () => {
    vi.spyOn(client, "listJobs").mockResolvedValue(catalogue([]));

    render(await HomePage());

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent(
      "You already have what these jobs want.",
    );
    expect(screen.getByRole("link", { name: "Browse the catalogue" })).toHaveAttribute(
      "href",
      "/jobs",
    );
    expect(screen.getByRole("link", { name: "Build your profile" })).toHaveAttribute(
      "href",
      "/onboarding",
    );
  });

  it("shows real postings from the catalogue", async () => {
    vi.spyOn(client, "listJobs").mockResolvedValue(catalogue([JOB]));

    render(await HomePage());

    expect(screen.getByRole("list", { name: "Recent postings" })).toHaveTextContent(
      "Remote Data Engineer",
    );
    expect(screen.getByRole("link", { name: /Remote Data Engineer/ })).toHaveAttribute(
      "href",
      "/jobs/job-1",
    );
  });

  it("still renders when the catalogue cannot be reached", async () => {
    // The rail is the page's content, not its reason to exist. An API that is
    // down costs the rail and must not cost the landing page.
    vi.spyOn(client, "listJobs").mockRejectedValue(new Error("unreachable"));

    render(await HomePage());

    expect(screen.getByRole("heading", { level: 1 })).toBeVisible();
    expect(screen.queryByRole("list", { name: "Recent postings" })).toBeNull();
  });

  it("explains the sequence in order", async () => {
    vi.spyOn(client, "listJobs").mockResolvedValue(catalogue([]));

    render(await HomePage());

    const steps = screen.getByRole("list", { name: "How the matching works" });
    expect(steps.children[0]).toHaveTextContent("Say what you can do");
  });

  it("asks an anonymous reader to register, and a signed-in one to look", async () => {
    vi.spyOn(client, "listJobs").mockResolvedValue(catalogue([]));

    const anonymous = render(await HomePage());
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute(
      "href",
      "/register",
    );
    anonymous.unmount();

    currentAccount.mockResolvedValue({ id: "u1", email: "a@b.co" });
    render(await HomePage());

    expect(screen.getByRole("link", { name: "See your matches" })).toHaveAttribute(
      "href",
      "/matches",
    );
    expect(screen.queryByRole("link", { name: "Create an account" })).toBeNull();
  });
});
