import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { JobSummary } from "@/lib/api/types";

import { JobRail } from "./job-rail";

function job(id: string, overrides: Partial<JobSummary> = {}): JobSummary {
  return {
    id,
    company: { id: "c1", display_name: "Meridian Software", website_url: null },
    title: `Job ${id}`,
    excerpt: "",
    location: "Berlin",
    workplace_type: "remote",
    employment_type: "full-time",
    application_url: "https://example.com",
    published_at: null,
    sources: [],
    ...overrides,
  };
}

describe("JobRail", () => {
  it("renders nothing at all when there is nothing to show", () => {
    const { container } = render(<JobRail jobs={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("links each posting to its own page", () => {
    render(<JobRail jobs={[job("1"), job("2")]} />);

    expect(screen.getByRole("link", { name: /Job 1/ })).toHaveAttribute("href", "/jobs/1");
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
  });

  it("omits the separator when a posting has no location", () => {
    render(<JobRail jobs={[job("1", { location: null })]} />);

    expect(screen.getByRole("link", { name: /Job 1/ })).toHaveTextContent("Meridian Software");
    expect(screen.queryByText(/·/)).toBeNull();
  });

  it("shows a posting's source, without nesting it inside the card's own link", () => {
    render(
      <JobRail
        jobs={[
          job("1", {
            sources: [
              { key: "arbeitnow", display_name: "Arbeitnow", url: "https://arbeitnow.example.com/jobs/1" },
            ],
          }),
        ]}
      />,
    );

    const sourceLink = screen.getByRole("link", { name: /^Arbeitnow/ });
    expect(sourceLink).toHaveAttribute("href", "https://arbeitnow.example.com/jobs/1");
    // Nesting an anchor inside the card's own anchor would be invalid HTML.
    expect(sourceLink.closest('a[href="/jobs/1"]')).toBeNull();
  });
});
