import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import { ApiUnreachableError } from "@/lib/api/errors";
import type { JobPage, JobSummary } from "@/lib/api/types";

import { JobList } from "./job-list";

// Counted as articles rather than list items: each card nests a list of
// attribute badges, so list items outnumber jobs.
function job(id: string, title = `Job ${id}`): JobSummary {
  return {
    id,
    company: { id: "company-1", display_name: "Acme GmbH", website_url: null },
    title,
    excerpt: "Work.",
    location: "Berlin",
    workplace_type: "remote",
    employment_type: "full-time",
    application_url: `https://acme.example.com/jobs/${id}`,
    published_at: "2026-08-01T12:00:00Z",
  };
}

function page(items: JobSummary[], next: string | null = null): JobPage {
  return { items, next_cursor: next };
}

beforeEach(() => {
  // The sentinel is never intersecting here, so loading is driven by the
  // button. The observer's own behaviour belongs to the browser test.
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      observe() {}
      disconnect() {}
      unobserve() {}
    },
  );
});

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("JobList", () => {
  it("renders the batch the server already fetched", () => {
    render(<JobList initial={page([job("1"), job("2")])} filters={{}} />);

    expect(screen.getAllByRole("article")).toHaveLength(2);
  });

  it("says so when nothing matches, rather than showing an empty page", () => {
    render(<JobList initial={page([])} filters={{}} />);

    expect(screen.getByText(/No jobs match these filters/)).toBeInTheDocument();
  });

  it("offers no way onward once the listing is complete", () => {
    render(<JobList initial={page([job("1")], null)} filters={{}} />);

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("appends the next batch rather than replacing what is shown", async () => {
    vi.spyOn(client, "listJobs").mockResolvedValue(page([job("3"), job("4")], null));
    render(<JobList initial={page([job("1"), job("2")], "cursor-1")} filters={{}} />);

    await userEvent.click(screen.getByRole("button", { name: /Show more/ }));

    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(4));
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("continues from the cursor it was given, inside the same filter set", async () => {
    const listJobs = vi.spyOn(client, "listJobs").mockResolvedValue(page([job("3")], null));
    const filters = { workplaceTypes: ["remote"] as const };
    render(<JobList initial={page([job("1")], "cursor-1")} filters={filters} />);

    await userEvent.click(screen.getByRole("button", { name: /Show more/ }));

    await waitFor(() => expect(listJobs).toHaveBeenCalledOnce());
    expect(listJobs.mock.calls[0][0]).toMatchObject({ cursor: "cursor-1", filters });
  });

  it("does not render a job twice if a batch arrives twice", async () => {
    vi.spyOn(client, "listJobs").mockResolvedValue(page([job("1"), job("2")], null));
    render(<JobList initial={page([job("1")], "cursor-1")} filters={{}} />);

    await userEvent.click(screen.getByRole("button", { name: /Show more/ }));

    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(2));
  });

  it("reports a failure without discarding what the reader already has", async () => {
    vi.spyOn(client, "listJobs").mockRejectedValue(new ApiUnreachableError());
    render(<JobList initial={page([job("1")], "cursor-1")} filters={{}} />);

    await userEvent.click(screen.getByRole("button", { name: /Show more/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/could not be reached/);
    expect(screen.getAllByRole("article")).toHaveLength(1);
  });

  it("resumes from the same cursor after a failure rather than starting over", async () => {
    const listJobs = vi
      .spyOn(client, "listJobs")
      .mockRejectedValueOnce(new ApiUnreachableError())
      .mockResolvedValueOnce(page([job("2")], null));
    render(<JobList initial={page([job("1")], "cursor-1")} filters={{}} />);

    await userEvent.click(screen.getByRole("button", { name: /Show more/ }));
    await screen.findByRole("alert");
    await userEvent.click(screen.getByRole("button", { name: /Try again/ }));

    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(2));
    expect(listJobs.mock.calls[1][0]).toMatchObject({ cursor: "cursor-1" });
  });

  it("describes an unrecognised failure rather than showing nothing", async () => {
    vi.spyOn(client, "listJobs").mockRejectedValue(new Error("kaboom"));
    render(<JobList initial={page([job("1")], "cursor-1")} filters={{}} />);

    await userEvent.click(screen.getByRole("button", { name: /Show more/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/Something went wrong/);
  });

  it("replaces the accumulated batches when the filters change", async () => {
    const { rerender } = render(
      <JobList initial={page([job("1"), job("2")], "cursor-1")} filters={{}} />,
    );
    expect(screen.getAllByRole("article")).toHaveLength(2);

    // A different filter set is a different listing, so what was collected for
    // the previous one must not survive into it.
    rerender(<JobList initial={page([job("9")], null)} filters={{ query: "engineer" }} />);

    await waitFor(() => expect(screen.getAllByRole("article")).toHaveLength(1));
  });

  it("tells a screen reader how much is on the page", () => {
    render(<JobList initial={page([job("1"), job("2")])} filters={{}} />);

    expect(screen.getByText("Showing 2 jobs")).toBeInTheDocument();
  });
});
