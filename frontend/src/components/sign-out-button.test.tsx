import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SignOutButton } from "./sign-out-button";

const signOut = vi.hoisted(() => vi.fn());
const replace = vi.hoisted(() => vi.fn());

vi.mock("@/lib/api/auth", () => ({ signOut }));

describe("SignOutButton", () => {
  beforeEach(() => {
    signOut.mockReset().mockResolvedValue(undefined);
    replace.mockReset();
    vi.stubGlobal("location", { replace });
  });
  afterEach(() => vi.unstubAllGlobals());

  it("ends this session and replaces the document", async () => {
    render(<SignOutButton />);

    await userEvent.click(screen.getByRole("button"));

    // Replaced, not pushed: the router cache still holds pages rendered for the
    // session that just ended, and Back must not be able to show them.
    await waitFor(() => expect(replace).toHaveBeenCalledWith("/"));
    expect(signOut).toHaveBeenCalledOnce();
  });

  it("says so and stays put when signing out fails", async () => {
    signOut.mockRejectedValue(new Error("offline"));
    render(<SignOutButton />);

    await userEvent.click(screen.getByRole("button"));

    expect(await screen.findByRole("alert")).toHaveTextContent("Signing out failed. Try again.");
    expect(replace).not.toHaveBeenCalled();
    // Still offered, because the session is still open.
    expect(screen.getByRole("button")).toBeEnabled();
  });
});
