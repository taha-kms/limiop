import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CVPage from "./page";

const cookies = vi.hoisted(() => vi.fn());
const redirect = vi.hoisted(() =>
  vi.fn((to: string) => {
    throw new Error(`REDIRECT:${to}`);
  }),
);

vi.mock("next/headers", () => ({ cookies }));
vi.mock("next/navigation", () => ({ redirect }));

const fetchMock = vi.fn();

function storedCV(state: string) {
  return {
    id: "cv-1",
    media_type: "application/pdf",
    size_bytes: 204800,
    processing_state: state,
    created_at: "2026-08-29T10:00:00Z",
  };
}

beforeEach(() => {
  fetchMock.mockReset();
  cookies.mockReset().mockResolvedValue({ toString: () => "session=signed" });
  redirect.mockClear();
  vi.stubGlobal("fetch", fetchMock);
  vi.stubEnv("SKILLSYNC_API_URL", "http://api:8000");
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("CVPage", () => {
  it("offers an upload when there is no CV yet", async () => {
    fetchMock.mockResolvedValue(Response.json(null));

    render(await CVPage());

    expect(screen.getByRole("button", { name: "Upload CV" })).toBeVisible();
    expect(screen.getByLabelText("Your CV")).toBeVisible();
  });

  it("states the limits before an upload is refused", async () => {
    fetchMock.mockResolvedValue(Response.json(null));

    render(await CVPage());

    expect(screen.getByText(/PDF, up to 5 MB/)).toBeVisible();
  });

  it("says a processed CV added its skills, and what it never removes", async () => {
    fetchMock.mockResolvedValue(Response.json(storedCV("processed")));

    render(await CVPage());

    expect(screen.getByRole("heading", { name: "Read" })).toBeVisible();
    expect(screen.getByText(/never removes a skill you picked by hand/)).toBeVisible();
    expect(screen.getByRole("button", { name: "Replace CV" })).toBeVisible();
  });

  it.each(["pending", "processing"])("shows %s as one thing a reader can act on", async (state) => {
    fetchMock.mockResolvedValue(Response.json(storedCV(state)));

    render(await CVPage());

    expect(screen.getByRole("heading", { name: "Being read" })).toBeVisible();
  });

  it("tells a failed CV what to do about it", async () => {
    fetchMock.mockResolvedValue(Response.json(storedCV("failed")));

    render(await CVPage());

    expect(screen.getByRole("heading", { name: "Could not be read" })).toBeVisible();
    // Actionable, and it says the profile survived.
    expect(screen.getByText(/scanned rather than text/)).toBeVisible();
    expect(screen.getByText(/profile was left as it was/)).toBeVisible();
  });

  it("sends an anonymous visitor to sign in and back again", async () => {
    cookies.mockResolvedValue({ toString: () => "" });

    await expect(CVPage()).rejects.toThrow("REDIRECT:/sign-in?next=%2Fcv");
  });

  it("says the CV could not be loaded rather than offering a blank slate", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 500 }));

    render(await CVPage());

    expect(screen.getByRole("heading", { name: "Your CV could not be loaded" })).toBeVisible();
    expect(screen.queryByRole("button", { name: "Upload CV" })).toBeNull();
  });
});
