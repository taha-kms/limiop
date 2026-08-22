import { describe, expect, it } from "vitest";

import { employmentLabel, publishedLabel, workplaceLabel } from "./format";

describe("workplaceLabel", () => {
  it.each([
    ["remote", "Remote"],
    ["hybrid", "Hybrid"],
    ["onsite", "On site"],
    ["unspecified", "Not stated"],
  ])("names %s", (value, expected) => {
    expect(workplaceLabel(value)).toBe(expected);
  });

  it("shows an unknown value rather than hiding it", () => {
    expect(workplaceLabel("underwater")).toBe("underwater");
  });
});

describe("employmentLabel", () => {
  it.each([
    ["full-time", "Full time"],
    ["internship", "Internship"],
    ["unspecified", "Not stated"],
  ])("names %s", (value, expected) => {
    expect(employmentLabel(value)).toBe(expected);
  });

  it("shows an unknown value rather than hiding it", () => {
    expect(employmentLabel("eternal")).toBe("eternal");
  });
});

describe("publishedLabel", () => {
  it("renders a date a reader can scan", () => {
    expect(publishedLabel("2026-08-01T12:00:00Z")).toBe("1 Aug 2026");
  });

  it("renders the same string wherever it runs", () => {
    // Fixed locale and time zone. The server and the browser both render this,
    // and disagreeing would be a hydration mismatch.
    expect(publishedLabel("2026-08-01T23:30:00Z")).toBe("1 Aug 2026");
  });

  it("has nothing to show for a job with no date", () => {
    expect(publishedLabel(null)).toBeNull();
  });

  it("has nothing to show for a value that is not a date", () => {
    expect(publishedLabel("not a date")).toBeNull();
  });
});
