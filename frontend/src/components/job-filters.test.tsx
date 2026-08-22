import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { JobFilters } from "./job-filters";

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
