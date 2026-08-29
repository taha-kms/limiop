import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import type { JobPage, JobSummary } from "@/lib/api/types";

import JobsPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

function job(id: string): JobSummary {
  return {
    id,
    company: { id: "company-1", display_name: "Acme GmbH", website_url: null },
    title: `Job ${id}`,
    excerpt: "Work.",
    location: "Berlin",
    workplace_type: "remote",
    employment_type: "full-time",
    application_url: `https://acme.example.com/jobs/${id}`,
    published_at: "2026-08-01T12:00:00Z",
  };
}

/** Render the server component the way the framework would: awaited. */
async function renderPage(searchParams: Record<string, string | string[]> = {}) {
  const element = await JobsPage({
    searchParams: Promise.resolve(searchParams),
    params: Promise.resolve({}),
  } as Parameters<typeof JobsPage>[0]);
  return render(element);
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("JobsPage", () => {
  beforeEach(() => {
    vi.spyOn(client, "listSources").mockResolvedValue([
      { key: "greenhouse", display_name: "Greenhouse" },
    ]);
  });

  it("renders the first batch on the server, so the page arrives with results", async () => {
    const page: JobPage = { items: [job("1"), job("2")], next_cursor: null };
    vi.spyOn(client, "listJobs").mockResolvedValue(page);

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Jobs");
    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("asks the API for exactly the filters in the URL", async () => {
    const listJobs = vi
      .spyOn(client, "listJobs")
      .mockResolvedValue({ items: [], next_cursor: null });

    await renderPage({ q: "engineer", workplace_type: ["remote", "hybrid"] });

    expect(listJobs).toHaveBeenCalledWith({
      filters: {
        query: "engineer",
        location: undefined,
        companyId: undefined,
        workplaceTypes: ["remote", "hybrid"],
        employmentTypes: [],
      },
      limit: 20,
    });
  });

  it("drops a filter value the API would reject", async () => {
    const listJobs = vi
      .spyOn(client, "listJobs")
      .mockResolvedValue({ items: [], next_cursor: null });

    await renderPage({ workplace_type: "underwater" });

    expect(listJobs.mock.calls[0][0]?.filters?.workplaceTypes).toEqual([]);
  });

  it("narrows to a board the catalogue ingests", async () => {
    const listJobs = vi
      .spyOn(client, "listJobs")
      .mockResolvedValue({ items: [], next_cursor: null });

    await renderPage({ source: "greenhouse" });

    expect(listJobs.mock.calls[0][0]?.filters?.source).toBe("greenhouse");
    expect(screen.getByLabelText("Source")).toBeInTheDocument();
  });

  it("drops a board nothing ingests rather than asking for a rejected listing", async () => {
    const listJobs = vi
      .spyOn(client, "listJobs")
      .mockResolvedValue({ items: [], next_cursor: null });

    await renderPage({ source: "notaboard" });

    expect(listJobs.mock.calls[0][0]?.filters?.source).toBeUndefined();
  });

  it("still lists the catalogue when the boards could not be read", async () => {
    // The boards are a filter option. Losing them costs a dropdown, not a page.
    vi.spyOn(client, "listSources").mockRejectedValue(new Error("unreachable"));
    vi.spyOn(client, "listJobs").mockResolvedValue({ items: [job("1")], next_cursor: null });

    await renderPage();

    expect(screen.getAllByRole("article")).toHaveLength(1);
    expect(screen.queryByLabelText("Source")).toBeNull();
  });

  it("says so when the catalogue has nothing to show", async () => {
    vi.spyOn(client, "listJobs").mockResolvedValue({ items: [], next_cursor: null });

    await renderPage();

    expect(screen.getByText(/No jobs match these filters/)).toBeInTheDocument();
  });

  it("lets a failure reach the error boundary rather than rendering half a page", async () => {
    vi.spyOn(client, "listJobs").mockRejectedValue(new Error("unreachable"));

    await expect(renderPage()).rejects.toThrowError();
  });
});
