import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignOutEverywhereButton } from "./sign-out-everywhere-button";

const replace = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  Object.defineProperty(window, "location", { configurable: true, value: { replace } });
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

describe("SignOutEverywhereButton", () => {
  it("calls the route that ends every session, not the one that clears a cookie", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    render(<SignOutEverywhereButton />);

    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere" }));

    expect(fetch).toHaveBeenCalledWith(
      "/api/auth/session/all",
      expect.objectContaining({ method: "DELETE", credentials: "same-origin" }),
    );
    // A full document load, so Back cannot show a page rendered for the
    // session that just ended.
    expect(replace).toHaveBeenCalledWith("/");
  });

  it("says this device goes too, which is what separates it from signing out", () => {
    render(<SignOutEverywhereButton />);

    expect(screen.getByText(/including this one/)).toBeVisible();
  });

  it("keeps the reader here when it fails, rather than pretending it worked", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 500 }));
    render(<SignOutEverywhereButton />);

    await userEvent.click(screen.getByRole("button", { name: "Sign out everywhere" }));

    expect(await screen.findByRole("alert")).toBeVisible();
    expect(replace).not.toHaveBeenCalled();
  });
});
