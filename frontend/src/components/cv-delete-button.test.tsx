import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CVDeleteButton } from "./cv-delete-button";

const reload = vi.fn();

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
  Object.defineProperty(window, "location", {
    configurable: true,
    value: { reload },
  });
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.clearAllMocks();
});

async function confirmDelete() {
  await userEvent.click(screen.getByRole("button", { name: "Delete CV" }));
  await userEvent.click(screen.getByRole("button", { name: /Yes, delete it/ }));
}

describe("CVDeleteButton", () => {
  it("asks before deleting, because deleting cannot be undone", async () => {
    render(<CVDeleteButton cvId="cv-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Delete CV" }));

    expect(fetch).not.toHaveBeenCalled();
    expect(screen.getByText(/Skills you picked by hand stay/)).toBeVisible();
  });

  it("deletes the CV it was given rather than whichever is newest", async () => {
    vi.mocked(fetch).mockResolvedValue(new Response(null, { status: 204 }));
    render(<CVDeleteButton cvId="cv 1/2" />);

    await confirmDelete();

    expect(fetch).toHaveBeenCalledWith(
      "/api/cv?id=cv%201%2F2",
      expect.objectContaining({ method: "DELETE", credentials: "same-origin" }),
    );
    expect(reload).toHaveBeenCalledOnce();
  });

  it("lets the reader back out", async () => {
    render(<CVDeleteButton cvId="cv-1" />);

    await userEvent.click(screen.getByRole("button", { name: "Delete CV" }));
    await userEvent.click(screen.getByRole("button", { name: "Keep it" }));

    expect(screen.getByRole("button", { name: "Delete CV" })).toBeVisible();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("says a CV already gone is gone rather than that something broke", async () => {
    vi.mocked(fetch).mockResolvedValue(Response.json({ detail: "no such CV" }, { status: 404 }));
    render(<CVDeleteButton cvId="cv-1" />);

    await confirmDelete();

    expect(screen.getByRole("alert")).toHaveTextContent("already gone");
    expect(reload).not.toHaveBeenCalled();
  });

  it("keeps the page usable when the delete fails", async () => {
    vi.mocked(fetch).mockRejectedValue(new TypeError("network"));
    render(<CVDeleteButton cvId="cv-1" />);

    await confirmDelete();

    expect(screen.getByRole("alert")).toHaveTextContent("could not be deleted");
    expect(screen.getByRole("button", { name: /Yes, delete it/ })).toBeEnabled();
  });
});
