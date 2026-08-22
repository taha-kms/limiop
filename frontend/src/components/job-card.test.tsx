import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { JobSummary } from "@/lib/api/types";

import { JobCard } from "./job-card";

function job(overrides: Partial<JobSummary> = {}): JobSummary {
  return {
    id: "job-1",
    company: { id: "company-1", display_name: "Acme GmbH", website_url: null },
    title: "Senior Data Engineer",
    excerpt: "Build reliable data pipelines.",
    location: "Berlin",
    workplace_type: "remote",
    employment_type: "full-time",
    application_url: "https://acme.example.com/jobs/1",
    published_at: "2026-08-01T12:00:00Z",
    ...overrides,
  };
}

describe("JobCard", () => {
  it("shows what a reader scans for", () => {
    render(<JobCard job={job()} />);

    expect(screen.getByRole("heading")).toHaveTextContent("Senior Data Engineer");
    expect(screen.getByText(/Acme GmbH/)).toBeInTheDocument();
    expect(screen.getByText(/Berlin/)).toBeInTheDocument();
    expect(screen.getByText("Build reliable data pipelines.")).toBeInTheDocument();
    expect(screen.getByText("Remote")).toBeInTheDocument();
    expect(screen.getByText("Full time")).toBeInTheDocument();
  });

  it("opens the job from its title", () => {
    render(<JobCard job={job()} />);

    expect(screen.getByRole("link", { name: "Senior Data Engineer" })).toHaveAttribute(
      "href",
      "/jobs/job-1",
    );
  });

  it("sends the reader to the employer, without a handle on this tab", () => {
    render(<JobCard job={job()} />);
    const link = screen.getByRole("link", { name: /Apply on the/ });

    expect(link).toHaveAttribute("href", "https://acme.example.com/jobs/1");
    expect(link).toHaveAttribute("target", "_blank");
    // noopener stops the opened page reaching back through window.opener, and
    // nofollow stops a provider link inheriting this site's ranking.
    expect(link.getAttribute("rel")).toContain("noopener");
    expect(link.getAttribute("rel")).toContain("noreferrer");
    expect(link.getAttribute("rel")).toContain("nofollow");
  });

  it("names the job in the link, so it is not one of many bare Apply links", () => {
    render(<JobCard job={job()} />);

    expect(
      screen.getByRole("link", { name: /Senior Data Engineer, opens in a new tab/ }),
    ).toBeInTheDocument();
  });

  it("renders a posting date the same way wherever it renders", () => {
    render(<JobCard job={job()} />);

    // Fixed locale and time zone: the server and the browser must agree or
    // hydration mismatches.
    expect(screen.getByText("Posted 1 Aug 2026")).toBeInTheDocument();
  });

  it("says so when a posting has no date rather than showing nothing", () => {
    render(<JobCard job={job({ published_at: null })} />);

    expect(screen.getByText("No posting date")).toBeInTheDocument();
  });

  it("omits the separator when a job has no location", () => {
    render(<JobCard job={job({ location: null })} />);

    expect(screen.getByText("Acme GmbH")).toBeInTheDocument();
  });

  it("renders a description as text, never as markup", () => {
    // Descriptions are flattened on ingestion, and React escapes regardless.
    // Both have to hold, because either alone is one mistake from a live tag.
    const { container } = render(
      <JobCard job={job({ excerpt: "<script>alert(1)</script> Real text" })} />,
    );

    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(/<script>alert\(1\)<\/script> Real text/)).toBeInTheDocument();
  });
});
