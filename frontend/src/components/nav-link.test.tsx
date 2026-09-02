import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { NavLink } from "./nav-link";

const usePathname = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({ usePathname }));

describe("NavLink", () => {
  beforeEach(() => usePathname.mockReset());

  it("marks the page you are on", () => {
    usePathname.mockReturnValue("/jobs");

    render(<NavLink href="/jobs">Jobs</NavLink>);

    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
  });

  it("marks a section you are inside, not only its index", () => {
    usePathname.mockReturnValue("/jobs/abc123");

    render(<NavLink href="/jobs">Jobs</NavLink>);

    expect(screen.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
  });

  it("leaves every other link unmarked", () => {
    usePathname.mockReturnValue("/insights");

    render(<NavLink href="/jobs">Jobs</NavLink>);

    expect(screen.getByRole("link", { name: "Jobs" })).not.toHaveAttribute("aria-current");
  });

  it("renders where there is no router rather than throwing", () => {
    // Typed as a string, and null in any tree without one.
    usePathname.mockReturnValue(null);

    render(<NavLink href="/jobs">Jobs</NavLink>);

    expect(screen.getByRole("link", { name: "Jobs" })).not.toHaveAttribute("aria-current");
  });
});
