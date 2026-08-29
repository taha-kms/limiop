import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getJob, listJobs, listSources, toSearchParams } from "./client";
import {
  ApiError,
  ApiUnreachableError,
  InvalidRequestError,
  JobNotFoundError,
  StaleCursorError,
  UnexpectedResponseError,
} from "./errors";
import type { JobDetail, JobPage, JobSummary } from "./types";

const summary: JobSummary = {
  id: "0193b4d2-0000-7000-8000-000000000001",
  company: {
    id: "0193b4d2-0000-7000-8000-000000000002",
    display_name: "Acme GmbH",
    website_url: null,
  },
  title: "Senior Data Engineer",
  excerpt: "Build reliable data pipelines.",
  location: "Berlin",
  workplace_type: "remote",
  employment_type: "full-time",
  application_url: "https://acme.example.com/jobs/1",
  published_at: "2026-08-01T12:00:00Z",
};

const detail: JobDetail = {
  ...summary,
  description: "Build reliable data pipelines, at length.",
  expires_at: null,
  status: "active",
  sources: [
    { key: "arbeitnow", display_name: "Arbeitnow", url: "https://arbeitnow.example.com/1" },
  ],
};

function respond(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json" },
  });
}

function stubFetch(...responses: (Response | Error | DOMException)[]): ReturnType<typeof vi.fn> {
  const remaining = [...responses];
  const stub = vi.fn(async () => {
    const next = remaining.shift();
    if (next === undefined) {
      throw new Error("fetch called more times than the test allows");
    }
    // Tested against Response rather than Error, because a DOMException is not
    // an instance of Error in every runtime and would be returned as a reply.
    if (next instanceof Response) {
      return next;
    }
    throw next;
  });
  vi.stubGlobal("fetch", stub);
  return stub;
}

function requestedUrl(stub: ReturnType<typeof vi.fn>, call = 0): URL {
  return new URL(stub.mock.calls[call][0] as string);
}

beforeEach(() => {
  vi.stubEnv("NEXT_PUBLIC_API_URL", "https://api.example.com");
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("toSearchParams", () => {
  it("asks for nothing it was not given", () => {
    expect(toSearchParams({}).toString()).toBe("");
  });

  it("repeats a vocabulary filter rather than joining it", () => {
    const params = toSearchParams({
      filters: { workplaceTypes: ["remote", "hybrid"], employmentTypes: ["internship"] },
    });

    expect(params.getAll("workplace_type")).toEqual(["remote", "hybrid"]);
    expect(params.getAll("employment_type")).toEqual(["internship"]);
  });

  it("omits an empty vocabulary filter rather than sending an empty value", () => {
    // The listing refuses unknown and empty parameters, so `workplace_type=`
    // would be a rejected request rather than an unfiltered one.
    const params = toSearchParams({ filters: { workplaceTypes: [], employmentTypes: [] } });

    expect(params.has("workplace_type")).toBe(false);
    expect(params.has("employment_type")).toBe(false);
  });

  it.each([
    ["location", { location: "" }],
    ["location", { location: "   " }],
    ["q", { query: "" }],
    ["q", { query: "  " }],
    ["company_id", { companyId: "" }],
  ])("omits %s when it is blank", (parameter, filters) => {
    expect(toSearchParams({ filters }).has(parameter)).toBe(false);
  });

  it("trims a search term rather than searching for the spaces", () => {
    expect(toSearchParams({ filters: { query: "  engineer  " } }).get("q")).toBe("engineer");
  });

  it("omits the cursor on the first page", () => {
    expect(toSearchParams({ cursor: null }).has("cursor")).toBe(false);
    expect(toSearchParams({ cursor: "" }).has("cursor")).toBe(false);
  });

  it("carries the cursor when continuing", () => {
    expect(toSearchParams({ cursor: "MXx8YQ" }).get("cursor")).toBe("MXx8YQ");
  });

  it("narrows to one source", () => {
    expect(toSearchParams({ filters: { source: "greenhouse" } }).get("source")).toBe("greenhouse");
  });

  it("omits an unset source rather than sending an empty one", () => {
    expect(toSearchParams({ filters: { source: "" } }).has("source")).toBe(false);
  });

  it("narrows to one company", () => {
    expect(toSearchParams({ filters: { companyId: "acme-id" } }).get("company_id")).toBe("acme-id");
  });

  it("omits the page size when the caller expresses no preference", () => {
    expect(toSearchParams({}).has("limit")).toBe(false);
  });
});

describe("listJobs", () => {
  it("returns the batch and the token that continues it", async () => {
    const page: JobPage = { items: [summary], next_cursor: "MXx8YQ" };
    stubFetch(respond(page));

    await expect(listJobs()).resolves.toEqual(page);
  });

  it("asks for twenty by default", async () => {
    const stub = stubFetch(respond({ items: [], next_cursor: null }));

    await listJobs();

    expect(requestedUrl(stub).searchParams.get("limit")).toBe("20");
  });

  it("builds the request against the configured API", async () => {
    const stub = stubFetch(respond({ items: [], next_cursor: null }));

    await listJobs({ filters: { location: "Berlin" }, limit: 5 });

    const url = requestedUrl(stub);
    expect(url.origin).toBe("https://api.example.com");
    expect(url.pathname).toBe("/jobs");
    expect(url.searchParams.get("location")).toBe("Berlin");
    expect(url.searchParams.get("limit")).toBe("5");
  });

  it("reports a stale cursor as its own failure, not a generic one", async () => {
    stubFetch(respond({ detail: "The cursor is not a position in this listing." }, 400));

    await expect(listJobs({ cursor: "nonsense" })).rejects.toBeInstanceOf(StaleCursorError);
  });

  it("reports a rejected request with what the API objected to", async () => {
    stubFetch(respond({ detail: "limit must be at least 1" }, 422));

    await expect(listJobs({ limit: 0 })).rejects.toThrowError(/limit must be at least 1/);
  });

  it("survives a rejection whose body is not the expected shape", async () => {
    stubFetch(new Response("<html>gateway</html>", { status: 422 }));

    await expect(listJobs()).rejects.toThrowError(/status 422/);
  });

  it("reports an unreachable API rather than surfacing a raw network error", async () => {
    stubFetch(new TypeError("Failed to fetch"));

    await expect(listJobs()).rejects.toBeInstanceOf(ApiUnreachableError);
  });

  it("reports a body that is not JSON as the service being unusable", async () => {
    stubFetch(new Response("not json", { status: 200 }));

    await expect(listJobs()).rejects.toBeInstanceOf(ApiUnreachableError);
  });

  it("reports an unhandled status rather than pretending it succeeded", async () => {
    stubFetch(respond({}, 503));

    await expect(listJobs()).rejects.toBeInstanceOf(UnexpectedResponseError);
  });

  it("lets an abort through, because the caller changed their mind", async () => {
    stubFetch(new DOMException("aborted", "AbortError"));

    await expect(listJobs()).rejects.toBeInstanceOf(DOMException);
  });
});

describe("listSources", () => {
  it("returns the boards the catalogue ingests", async () => {
    stubFetch(respond({ sources: [{ key: "greenhouse", display_name: "Greenhouse" }] }));

    await expect(listSources()).resolves.toEqual([
      { key: "greenhouse", display_name: "Greenhouse" },
    ]);
  });

  it("asks the listing which boards it has rather than holding a list", async () => {
    const stub = stubFetch(respond({ sources: [] }));

    await listSources();

    expect(requestedUrl(stub).pathname).toBe("/jobs/sources");
  });

  it("reports an unreachable API", async () => {
    stubFetch(new TypeError("Failed to fetch"));

    await expect(listSources()).rejects.toBeInstanceOf(ApiUnreachableError);
  });

  it("reports an unhandled status", async () => {
    stubFetch(respond({}, 500));

    await expect(listSources()).rejects.toBeInstanceOf(UnexpectedResponseError);
  });
});

describe("getJob", () => {
  it("returns the job", async () => {
    stubFetch(respond(detail));

    await expect(getJob(detail.id)).resolves.toEqual(detail);
  });

  it("escapes the identifier rather than pasting it into the path", async () => {
    const stub = stubFetch(respond(detail));

    await getJob("../jobs?evil=1");

    expect(requestedUrl(stub).pathname).toBe("/jobs/..%2Fjobs%3Fevil%3D1");
  });

  it("reports a missing job as its own failure, carrying what was asked for", async () => {
    stubFetch(respond({ detail: "No such job." }, 404));

    await expect(getJob("missing")).rejects.toMatchObject({
      name: "JobNotFoundError",
      jobId: "missing",
    });
  });

  it("reports a malformed identifier as a rejected request", async () => {
    stubFetch(respond({ detail: "not a valid uuid" }, 422));

    await expect(getJob("not-a-uuid")).rejects.toBeInstanceOf(InvalidRequestError);
  });

  it("reports an unreachable API", async () => {
    stubFetch(new TypeError("Failed to fetch"));

    await expect(getJob(detail.id)).rejects.toBeInstanceOf(ApiUnreachableError);
  });

  it("reports an unhandled status", async () => {
    stubFetch(respond({}, 500));

    await expect(getJob(detail.id)).rejects.toBeInstanceOf(UnexpectedResponseError);
  });
});

describe("the error taxonomy", () => {
  it("lets a caller treat every failure alike when it wants to", () => {
    for (const error of [
      new StaleCursorError(),
      new JobNotFoundError("x"),
      new InvalidRequestError("x"),
      new UnexpectedResponseError(500),
      new ApiUnreachableError(),
    ]) {
      expect(error).toBeInstanceOf(ApiError);
      expect(error.name).not.toBe("Error");
      expect(error.message).not.toBe("");
    }
  });
});
