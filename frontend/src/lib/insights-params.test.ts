import { describe, expect, it } from "vitest";

import {
  DEFAULT_WINDOW,
  parseInsightsFilters,
  toQueryString,
  windowStart,
} from "./insights-params";

const CATALOGUE = { sources: ["greenhouse", "arbeitnow"] };
const NOW = new Date("2026-08-29T12:00:00.000Z");

describe("parseInsightsFilters", () => {
  it("reads nothing from an empty query string", () => {
    expect(parseInsightsFilters({})).toEqual({ window: DEFAULT_WINDOW, source: undefined });
  });

  it("reads a window and a board the catalogue ingests", () => {
    expect(parseInsightsFilters({ window: "90d", source: "greenhouse" }, CATALOGUE)).toEqual({
      window: "90d",
      source: "greenhouse",
    });
  });

  it("falls back rather than asking the API a question it refuses", () => {
    expect(parseInsightsFilters({ window: "since forever" }).window).toBe(DEFAULT_WINDOW);
    expect(parseInsightsFilters({ source: "notaboard" }, CATALOGUE).source).toBeUndefined();
    expect(parseInsightsFilters({ source: "greenhouse" }).source).toBeUndefined();
  });
});

describe("windowStart", () => {
  it("counts back from the moment the page is rendered", () => {
    expect(windowStart("30d", NOW)).toBe("2026-07-30T12:00:00.000Z");
    expect(windowStart("90d", NOW)).toBe("2026-05-31T12:00:00.000Z");
    expect(windowStart("12m", NOW)).toBe("2025-08-29T12:00:00.000Z");
  });

  it("asks for no start at all when the window is the whole catalogue", () => {
    expect(windowStart("all", NOW)).toBeUndefined();
  });
});

describe("toQueryString", () => {
  it("survives a round trip, so a view is a link", () => {
    const filters = parseInsightsFilters({ window: "30d", source: "greenhouse" }, CATALOGUE);

    expect(parseInsightsFilters({ window: "30d", source: "greenhouse" }, CATALOGUE)).toEqual(
      filters,
    );
    expect(toQueryString(filters)).toBe("window=30d&source=greenhouse");
  });

  it("says nothing when nothing was chosen", () => {
    expect(toQueryString({ window: DEFAULT_WINDOW })).toBe("");
  });
});
