import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobFilters } from "./job-filters";

const SOURCES = [
  { key: "arbeitnow", display_name: "Arbeitnow" },
  { key: "greenhouse", display_name: "Greenhouse" },
];

const push = vi.fn();
let currentParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => currentParams,
}));

beforeEach(() => {
  currentParams = new URLSearchParams();
});

afterEach(() => {
  vi.clearAllMocks();
});

describe("JobFilters", () => {
  it("navigates to a URL carrying the chosen filters", async () => {
    render(<JobFilters />);

    await userEvent.type(screen.getByLabelText("Search job titles"), "engineer");
    await userEvent.click(screen.getByRole("checkbox", { name: "Remote" }));
    await userEvent.click(screen.getByRole("button", { name: /Apply filters/ }));

    expect(push).toHaveBeenCalledOnce();
    const url = new URL(push.mock.calls[0][0] as string, "https://skillsync.test");
    expect(url.pathname).toBe("/jobs");
    expect(url.searchParams.get("q")).toBe("engineer");
    expect(url.searchParams.getAll("workplace_type")).toEqual(["remote"]);
  });

  it("carries several values of one filter", async () => {
    render(<JobFilters />);

    await userEvent.click(screen.getByRole("checkbox", { name: "Remote" }));
    await userEvent.click(screen.getByRole("checkbox", { name: "Hybrid" }));
    await userEvent.click(screen.getByRole("button", { name: /Apply filters/ }));

    const url = new URL(push.mock.calls[0][0] as string, "https://skillsync.test");
    expect(url.searchParams.getAll("workplace_type")).toEqual(["remote", "hybrid"]);
  });

  it("omits a blank field rather than sending an empty value", async () => {
    // The listing refuses an empty value, so a blank box must mean no filter.
    render(<JobFilters />);

    await userEvent.type(screen.getByLabelText("Location"), "   ");
    await userEvent.click(screen.getByRole("button", { name: /Apply filters/ }));

    expect(push).toHaveBeenCalledWith("/jobs");
  });

  it("trims a term so the search is not for the spacing", async () => {
    render(<JobFilters />);

    await userEvent.type(screen.getByLabelText("Location"), "  Berlin  ");
    await userEvent.click(screen.getByRole("button", { name: /Apply filters/ }));

    const url = new URL(push.mock.calls[0][0] as string, "https://skillsync.test");
    expect(url.searchParams.get("location")).toBe("Berlin");
  });

  it("never carries a cursor, because a new filter set is a new listing", async () => {
    currentParams = new URLSearchParams("cursor=MXx8YQ&q=engineer");
    render(<JobFilters />);

    await userEvent.click(screen.getByRole("button", { name: /Apply filters/ }));

    const url = new URL(push.mock.calls[0][0] as string, "https://skillsync.test");
    expect(url.searchParams.has("cursor")).toBe(false);
    expect(url.searchParams.get("q")).toBe("engineer");
  });

  it("shows the filters already in the URL, so the form matches the results", () => {
    currentParams = new URLSearchParams("q=engineer&location=Berlin&workplace_type=hybrid");
    render(<JobFilters />);

    expect(screen.getByLabelText("Search job titles")).toHaveValue("engineer");
    expect(screen.getByLabelText("Location")).toHaveValue("Berlin");
    expect(screen.getByRole("checkbox", { name: "Hybrid" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "Remote" })).not.toBeChecked();
  });

  it("offers the boards the catalogue ingests", async () => {
    render(<JobFilters sources={SOURCES} />);

    await userEvent.selectOptions(screen.getByLabelText("Source"), "greenhouse");
    await userEvent.click(screen.getByRole("button", { name: /Apply filters/ }));

    const url = new URL(push.mock.calls[0][0] as string, "https://skillsync.test");
    expect(url.searchParams.get("source")).toBe("greenhouse");
  });

  it("treats any source as no filter rather than as an empty one", async () => {
    currentParams = new URLSearchParams("source=greenhouse");
    render(<JobFilters sources={SOURCES} />);

    await userEvent.selectOptions(screen.getByLabelText("Source"), "");
    await userEvent.click(screen.getByRole("button", { name: /Apply filters/ }));

    expect(push).toHaveBeenCalledWith("/jobs");
  });

  it("shows the source already in the URL", () => {
    currentParams = new URLSearchParams("source=arbeitnow");
    render(<JobFilters sources={SOURCES} />);

    expect(screen.getByLabelText("Source")).toHaveValue("arbeitnow");
  });

  it("offers no source filter when the boards could not be read", () => {
    // A dropdown holding only "any source" would be a filter that does nothing.
    render(<JobFilters />);

    expect(screen.queryByLabelText("Source")).toBeNull();
  });

  it("works without JavaScript, by submitting to the same route", () => {
    const { container } = render(<JobFilters />);
    const form = container.querySelector("form");

    expect(form).toHaveAttribute("method", "get");
    expect(form).toHaveAttribute("action", "/jobs");
  });

  it("offers a way back to the unfiltered listing", () => {
    render(<JobFilters />);

    expect(screen.getByRole("link", { name: "Clear" })).toHaveAttribute("href", "/jobs");
  });
});
