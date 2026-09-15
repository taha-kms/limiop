import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SourceAttribution } from "@/lib/api/types";

import { SourceLine } from "./source-line";

function source(overrides: Partial<SourceAttribution> = {}): SourceAttribution {
  return {
    key: "arbeitnow",
    display_name: "Arbeitnow",
    url: "https://arbeitnow.example.com/jobs/1",
    ...overrides,
  };
}

describe("SourceLine", () => {
  it("renders nothing for a job with no recorded source", () => {
    const { container } = render(<SourceLine sources={[]} />);

    expect(container).toBeEmptyDOMElement();
  });

  it("links a generic source by its display name", () => {
    render(<SourceLine sources={[source()]} />);

    const link = screen.getByRole("link", { name: "Arbeitnow" });
    expect(link).toHaveAttribute("href", "https://arbeitnow.example.com/jobs/1");
  });

  it("does not mark a generic source's link nofollow", () => {
    render(<SourceLine sources={[source()]} />);

    const link = screen.getByRole("link", { name: "Arbeitnow" });
    expect(link.getAttribute("rel")).not.toContain("nofollow");
  });

  it("separates several sources", () => {
    render(
      <SourceLine
        sources={[source(), source({ key: "jobicy", display_name: "Jobicy", url: "https://jobicy.example.com/jobs/9" })]}
      />,
    );

    expect(screen.getByRole("link", { name: "Arbeitnow" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Jobicy" })).toBeInTheDocument();
    expect(screen.getByText(/·/)).toBeInTheDocument();
  });

  it("renders the exact label Adzuna's terms require", () => {
    render(
      <SourceLine
        sources={[
          source({
            key: "adzuna",
            display_name: "Adzuna",
            url: "https://www.adzuna.co.uk/land/ad/12345",
          }),
        ]}
      />,
    );

    const jobsLink = screen.getByRole("link", { name: "Jobs" });
    expect(jobsLink).toHaveAttribute("href", "https://www.adzuna.co.uk");

    const logo = screen.getByRole("img", { name: "Adzuna" });
    expect(logo).toHaveAttribute("src", "/sources/adzuna.svg");
    expect(logo.closest("a")).toHaveAttribute("href", "https://www.adzuna.co.uk/land/ad/12345");

    expect(screen.getByText(/by/)).toBeInTheDocument();
  });

  it("does not mark Adzuna's links nofollow", () => {
    render(
      <SourceLine
        sources={[
          source({
            key: "adzuna",
            display_name: "Adzuna",
            url: "https://www.adzuna.co.uk/land/ad/12345",
          }),
        ]}
      />,
    );

    for (const link of screen.getAllByRole("link")) {
      expect(link.getAttribute("rel")).not.toContain("nofollow");
    }
  });
});
