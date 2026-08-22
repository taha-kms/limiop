import { describe, expect, it } from "vitest";

import { hasAnyFilter, parseFilters, toQueryString } from "./search-params";
import type { RawSearchParams } from "./search-params";

/** What Next would hand a page for this query string, arrays preserved. */
function asPageParams(query: string): RawSearchParams {
  const params = new URLSearchParams(query);
  return Object.fromEntries(
    [...new Set(params.keys())].map((key) => {
      const all = params.getAll(key);
      return [key, all.length > 1 ? all : all[0]];
    }),
  );
}

describe("parseFilters", () => {
  it("reads nothing from an empty query string", () => {
    expect(parseFilters({})).toEqual({
      companyId: undefined,
      location: undefined,
      query: undefined,
      workplaceTypes: [],
      employmentTypes: [],
    });
  });

  it("reads every filter the listing supports", () => {
    expect(
      parseFilters({
        q: "engineer",
        location: "Berlin",
        company_id: "acme-id",
        workplace_type: ["remote", "hybrid"],
        employment_type: "internship",
      }),
    ).toEqual({
      query: "engineer",
      location: "Berlin",
      companyId: "acme-id",
      workplaceTypes: ["remote", "hybrid"],
      employmentTypes: ["internship"],
    });
  });

  it("treats a blank value as absent rather than as a filter", () => {
    expect(parseFilters({ q: "   ", location: "" }).query).toBeUndefined();
    expect(parseFilters({ q: "   ", location: "" }).location).toBeUndefined();
  });

  it("trims a value so the search is for the term, not the spacing", () => {
    expect(parseFilters({ q: "  engineer  " }).query).toBe("engineer");
  });

  it("drops a value outside the vocabulary rather than passing it on", () => {
    // A hand-edited URL should narrow the listing oddly at worst. Forwarding an
    // unknown value would make the API reject the request instead.
    expect(parseFilters({ workplace_type: ["remote", "underwater"] }).workplaceTypes).toEqual([
      "remote",
    ]);
    expect(parseFilters({ employment_type: "eternal" }).employmentTypes).toEqual([]);
  });

  it("collapses a value repeated in the URL", () => {
    expect(parseFilters({ workplace_type: ["remote", "remote"] }).workplaceTypes).toEqual([
      "remote",
    ]);
  });

  it("ignores a cursor, because a page is not a filter", () => {
    expect(hasAnyFilter(parseFilters({ cursor: "MXx8YQ" }))).toBe(false);
  });
});

describe("toQueryString", () => {
  it("round-trips a filter set, so a link reproduces the view", () => {
    const filters = parseFilters({
      q: "engineer",
      location: "Berlin",
      company_id: "acme-id",
      workplace_type: ["remote", "hybrid"],
      employment_type: ["internship"],
    });

    expect(parseFilters(asPageParams(toQueryString(filters)))).toEqual(filters);
  });

  it("repeats a vocabulary filter so the API reads it as a list", () => {
    const query = toQueryString({ workplaceTypes: ["remote", "hybrid"] });

    expect(new URLSearchParams(query).getAll("workplace_type")).toEqual(["remote", "hybrid"]);
  });

  it("writes nothing for an unfiltered listing", () => {
    expect(toQueryString(parseFilters({}))).toBe("");
    expect(hasAnyFilter(parseFilters({}))).toBe(false);
  });
});
