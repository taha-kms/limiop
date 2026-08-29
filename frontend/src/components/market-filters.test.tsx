import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { MarketFilters } from "./market-filters";

const push = vi.fn();
let currentParams = new URLSearchParams();

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  useSearchParams: () => currentParams,
}));

const SOURCES = [{ key: "greenhouse", display_name: "Greenhouse" }];

beforeEach(() => {
  currentParams = new URLSearchParams();
});

afterEach(() => vi.clearAllMocks());

function pushedUrl(): URL {
  return new URL(push.mock.calls[0][0] as string, "https://skillsync.test");
}

describe("MarketFilters", () => {
  it("navigates to a URL carrying the window and the source", async () => {
    render(<MarketFilters sources={SOURCES} />);

    await userEvent.selectOptions(screen.getByLabelText("Window"), "90d");
    await userEvent.selectOptions(screen.getByLabelText("Source"), "greenhouse");
    await userEvent.click(screen.getByRole("button", { name: /Apply/ }));

    expect(pushedUrl().searchParams.get("window")).toBe("90d");
    expect(pushedUrl().searchParams.get("source")).toBe("greenhouse");
  });

  it("treats every source as no filter rather than as an empty one", async () => {
    currentParams = new URLSearchParams("source=greenhouse");
    render(<MarketFilters sources={SOURCES} />);

    await userEvent.selectOptions(screen.getByLabelText("Source"), "");
    await userEvent.click(screen.getByRole("button", { name: /Apply/ }));

    expect(pushedUrl().searchParams.has("source")).toBe(false);
  });

  it("shows the view already in the URL, so the controls match the figures", () => {
    currentParams = new URLSearchParams("window=30d&source=greenhouse");
    render(<MarketFilters sources={SOURCES} />);

    expect(screen.getByLabelText("Window")).toHaveValue("30d");
    expect(screen.getByLabelText("Source")).toHaveValue("greenhouse");
  });

  it("offers no source filter when the boards could not be read", () => {
    render(<MarketFilters />);

    expect(screen.queryByLabelText("Source")).toBeNull();
    expect(screen.getByLabelText("Window")).toBeVisible();
  });

  it("works without JavaScript, by submitting to the same route", () => {
    const { container } = render(<MarketFilters sources={SOURCES} />);
    const form = container.querySelector("form");

    expect(form).toHaveAttribute("method", "get");
    expect(form).toHaveAttribute("action", "/insights");
  });

  it("offers a way back to the whole market", () => {
    render(<MarketFilters sources={SOURCES} />);

    expect(screen.getByRole("link", { name: "Clear" })).toHaveAttribute("href", "/insights");
  });
});
