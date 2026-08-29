import { render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import InsightsPage from "./page";

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
  useSearchParams: () => new URLSearchParams(),
}));

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
const SOURCES = { sources: [{ key: "greenhouse", display_name: "Greenhouse" }] };

function serve(overrides: { skills?: object; sources?: object } = {}) {
  fetchMock.mockImplementation((url: string) => {
    if (url.includes("/jobs/sources")) {
      return Promise.resolve(Response.json(overrides.sources ?? SOURCES));
    }
    if (url.includes("/skills")) return Promise.resolve(Response.json(overrides.skills ?? SKILLS));
    if (url.includes("/locations")) return Promise.resolve(Response.json(LOCATIONS));
    return Promise.resolve(Response.json(TRENDS));
  });
}

/** Render the server component the way the framework would: awaited. */
function page(searchParams: Record<string, string | string[]> = {}) {
  return InsightsPage({
    searchParams: Promise.resolve(searchParams),
    params: Promise.resolve({}),
  } as Parameters<typeof InsightsPage>[0]);
}

function requestedUrls(): string[] {
  return fetchMock.mock.calls.map((call) => String(call[0]));
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

    render(await page());

    const skills = within(section("Most asked-for skills"));
    expect(skills.getByText("Python")).toBeVisible();
    expect(skills.getByText("40 jobs")).toBeVisible();
  });

  it("keeps the postings that stated no location", async () => {
    serve();

    render(await page());

    expect(within(section("Where the jobs are")).getByText("Unknown")).toBeVisible();
  });

  it("names the unstated arrangement rather than showing the enum", async () => {
    serve();

    render(await page());

    const workplace = within(section("How the work happens"));
    expect(workplace.getByText("Not stated")).toBeVisible();
    expect(workplace.queryByText("unspecified")).toBeNull();
  });

  it("labels a trend point by its month in UTC", async () => {
    serve();

    render(await page());

    expect(within(section("Postings over time")).getByText("January 2026")).toBeVisible();
  });

  it("says so when a section has nothing in it", async () => {
    serve({ skills: { skills: [] } });

    render(await page());

    expect(
      within(section("Most asked-for skills")).getByText("Nothing to show yet."),
    ).toBeVisible();
  });

  it("says the numbers could not be read rather than showing zeroes", async () => {
    // A market that looks empty and a market nobody could read are different
    // answers, and only one of them is about the market.
    fetchMock.mockResolvedValue(new Response(null, { status: 500 }));

    render(await page());

    expect(
      screen.getByRole("heading", { name: "These numbers could not be loaded" }),
    ).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Most asked-for skills" })).toBeNull();
  });

  it("says the same when the API cannot be reached at all", async () => {
    fetchMock.mockRejectedValue(new TypeError("network"));

    render(await page());

    expect(
      screen.getByRole("heading", { name: "These numbers could not be loaded" }),
    ).toBeVisible();
  });

  it("asks all three aggregates the same question", async () => {
    serve();

    await page({ window: "30d", source: "greenhouse" });

    const asked = requestedUrls().filter((url) => url.includes("/analytics/"));
    expect(asked).toHaveLength(3);
    for (const url of asked) {
      expect(url).toContain("source_key=greenhouse");
      expect(url).toContain("since=");
    }
  });

  it("asks for no window when the reader wants the whole catalogue", async () => {
    serve();

    await page();

    for (const url of requestedUrls().filter((asked) => asked.includes("/analytics/"))) {
      expect(url).not.toContain("since=");
      expect(url).not.toContain("source_key=");
    }
  });

  it("drops a filter the API would refuse rather than rendering an error", async () => {
    serve();

    await page({ window: "yesterday", source: "notaboard" });

    for (const url of requestedUrls().filter((asked) => asked.includes("/analytics/"))) {
      expect(url).not.toContain("since=");
      expect(url).not.toContain("source_key=");
    }
  });

  it("says what the figures are counting", async () => {
    serve();

    render(await page({ window: "30d", source: "greenhouse" }));

    expect(screen.getByText(/last 30 days, as listed by Greenhouse/)).toBeVisible();
  });

  it("still shows the figures when the boards could not be read", async () => {
    fetchMock.mockImplementation((url: string) => {
      if (url.includes("/jobs/sources")) {
        return Promise.resolve(new Response(null, { status: 500 }));
      }
      if (url.includes("/skills")) return Promise.resolve(Response.json(SKILLS));
      if (url.includes("/locations")) return Promise.resolve(Response.json(LOCATIONS));
      return Promise.resolve(Response.json(TRENDS));
    });

    render(await page());

    expect(screen.getByRole("heading", { name: "Most asked-for skills" })).toBeVisible();
    expect(screen.queryByLabelText("Source")).toBeNull();
  });
});
