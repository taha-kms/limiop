import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import * as client from "@/lib/api/client";
import { ApiUnreachableError, InvalidRequestError, JobNotFoundError } from "@/lib/api/errors";
import type { JobDetail } from "@/lib/api/types";

import JobDetailPage from "./page";

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});

vi.mock("next/navigation", () => ({ notFound: () => notFound() }));

function detail(overrides: Partial<JobDetail> = {}): JobDetail {
  return {
    id: "job-1",
    company: { id: "company-1", display_name: "Acme GmbH", website_url: null },
    title: "Senior Data Engineer",
    description: "Build reliable data pipelines.\nAnd a second paragraph.",
    location: "Berlin",
    workplace_type: "remote",
    employment_type: "full-time",
    application_url: "https://acme.example.com/jobs/1",
    published_at: "2026-08-01T12:00:00Z",
    expires_at: null,
    status: "active",
    sources: [
      { key: "arbeitnow", display_name: "Arbeitnow", url: "https://arbeitnow.example.com/1" },
    ],
    ...overrides,
  };
}

async function renderPage(jobId = "job-1") {
  const element = await JobDetailPage({
    params: Promise.resolve({ jobId }),
    searchParams: Promise.resolve({}),
  } as Parameters<typeof JobDetailPage>[0]);
  return render(element);
}

afterEach(() => {
  vi.restoreAllMocks();
  notFound.mockClear();
});

describe("JobDetailPage", () => {
  it("shows the whole posting, not the excerpt", async () => {
    vi.spyOn(client, "getJob").mockResolvedValue(detail());

    await renderPage();

    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("Senior Data Engineer");
    expect(screen.getByText(/And a second paragraph/)).toBeInTheDocument();
    expect(screen.getByText("Remote")).toBeInTheDocument();
    expect(screen.getByText("Full time")).toBeInTheDocument();
  });

  it("asks for the job in the URL", async () => {
    const getJob = vi.spyOn(client, "getJob").mockResolvedValue(detail());

    await renderPage("some-identifier");

    expect(getJob).toHaveBeenCalledWith("some-identifier");
  });

  it("names each board and links to the original posting", async () => {
    vi.spyOn(client, "getJob").mockResolvedValue(
      detail({
        sources: [
          { key: "arbeitnow", display_name: "Arbeitnow", url: "https://arbeitnow.example.com/1" },
          { key: "jobicy", display_name: "Jobicy", url: "https://jobicy.example.com/9" },
        ],
      }),
    );

    await renderPage();

    const arbeitnow = screen.getByRole("link", { name: /Arbeitnow/ });
    expect(arbeitnow).toHaveAttribute("href", "https://arbeitnow.example.com/1");
    expect(arbeitnow.getAttribute("rel")).toContain("noopener");
    expect(screen.getByRole("link", { name: /Jobicy/ })).toBeInTheDocument();
  });

  it("omits the attribution section for a job with no recorded source", async () => {
    vi.spyOn(client, "getJob").mockResolvedValue(detail({ sources: [] }));

    await renderPage();

    expect(screen.queryByText("Where this was found")).not.toBeInTheDocument();
  });

  it.each([
    ["expired", /expired/i],
    ["removed", /withdrawn/i],
  ] as const)("says a %s posting is no longer open rather than hiding it", async (status, said) => {
    vi.spyOn(client, "getJob").mockResolvedValue(detail({ status }));

    await renderPage();

    expect(screen.getByRole("status")).toHaveTextContent(said);
  });

  it("shows no notice for a job that is still open", async () => {
    vi.spyOn(client, "getJob").mockResolvedValue(detail());

    await renderPage();

    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("renders a not-found page when no job has that identifier", async () => {
    vi.spyOn(client, "getJob").mockRejectedValue(new JobNotFoundError("missing"));

    await expect(renderPage("missing")).rejects.toThrowError("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledOnce();
  });

  it("renders not-found for an identifier the API will not parse", async () => {
    // The identifier is the only thing this route sends, so a rejected request
    // means the link is wrong. Offering a retry would invite a reader to retry
    // something that cannot start working.
    vi.spyOn(client, "getJob").mockRejectedValue(new InvalidRequestError("not a valid uuid"));

    await expect(renderPage("not-a-uuid")).rejects.toThrowError("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalledOnce();
  });

  it("lets any other failure reach the error boundary", async () => {
    // A missing job is a page. An unreachable service is a failure, and
    // rendering it as not-found would tell the reader something untrue.
    vi.spyOn(client, "getJob").mockRejectedValue(new ApiUnreachableError());

    await expect(renderPage()).rejects.toBeInstanceOf(ApiUnreachableError);
    expect(notFound).not.toHaveBeenCalled();
  });

  it("renders provider text as text, never as markup", async () => {
    vi.spyOn(client, "getJob").mockResolvedValue(
      detail({ description: "<script>alert(1)</script> Real text" }),
    );

    const { container } = await renderPage();

    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText(/<script>alert\(1\)<\/script> Real text/)).toBeInTheDocument();
  });

  it("offers a way back to the listing", async () => {
    vi.spyOn(client, "getJob").mockResolvedValue(detail());

    await renderPage();

    expect(screen.getByRole("link", { name: /All jobs/ })).toHaveAttribute("href", "/jobs");
  });
});
