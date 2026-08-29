import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InsightsPage from "./page";

/**
 * Driven through `fetch` rather than by mocking the client.
 *
 * The page and its reader are the unit worth testing together: mocking the
 * client would leave the parsing, the three concurrent reads, and the failure
 * classification untested, and those are where this page can actually be wrong.
 */
const fetchMock = vi.fn();

const SKILLS = {
  skills: [
    { concept_id: "s1", preferred_label: "Python", jobs: 40 },
    { concept_id: "s2", preferred_label: "SQL", jobs: 10 },
  ],
};
const LOCATIONS = {
  locations: [
    { location: "Berlin", jobs: 30 },
    { location: "Unknown", jobs: 5 },
  ],
  workplace_types: [
    { workplace_type: "unspecified", jobs: 25 },
    { workplace_type: "remote", jobs: 10 },
  ],
};
const TRENDS = { bucket: "month", points: [{ bucket_start: "2026-01-01T00:00:00Z", jobs: 12 }] };

function serve(overrides: { skills?: object } = {}) {
  fetchMock.mockImplementation((url: string) => {
    if (url.includes("/skills")) return Promise.resolve(Response.json(overrides.skills ?? SKILLS));
    if (url.includes("/locations")) return Promise.resolve(Response.json(LOCATIONS));
    return Promise.resolve(Response.json(TRENDS));
  });
}

function section(name: string) {
  return screen.getByRole("heading", { name }).closest("section") as HTMLElement;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("InsightsPage", () => {
  it("ranks the skills the market asks for", async () => {
    serve();

    render(await InsightsPage());

    const skills = within(section("Most asked-for skills"));
    expect(skills.getByText("Python")).toBeVisible();
    expect(skills.getByText("40 jobs")).toBeVisible();
  });

  it("keeps the postings that stated no location", async () => {
    serve();

    render(await InsightsPage());

    expect(within(section("Where the jobs are")).getByText("Unknown")).toBeVisible();
  });

  it("names the unstated arrangement rather than showing the enum", async () => {
    serve();

    render(await InsightsPage());

    const workplace = within(section("How the work happens"));
    expect(workplace.getByText("Not stated")).toBeVisible();
    expect(workplace.queryByText("unspecified")).toBeNull();
  });

  it("labels a trend point by its month in UTC", async () => {
    serve();

    render(await InsightsPage());

    expect(within(section("Postings over time")).getByText("January 2026")).toBeVisible();
  });

  it("says so when a section has nothing in it", async () => {
    serve({ skills: { skills: [] } });

    render(await InsightsPage());

    expect(
      within(section("Most asked-for skills")).getByText("Nothing to show yet."),
    ).toBeVisible();
  });

  it("says the numbers could not be read rather than showing zeroes", async () => {
    // A market that looks empty and a market nobody could read are different
    // answers, and only one of them is about the market.
    fetchMock.mockResolvedValue(new Response(null, { status: 500 }));

    render(await InsightsPage());

    expect(
      screen.getByRole("heading", { name: "These numbers could not be loaded" }),
    ).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Most asked-for skills" })).toBeNull();
  });

  it("says the same when the API cannot be reached at all", async () => {
    fetchMock.mockRejectedValue(new TypeError("network"));

    render(await InsightsPage());

    expect(
      screen.getByRole("heading", { name: "These numbers could not be loaded" }),
    ).toBeVisible();
  });
});
