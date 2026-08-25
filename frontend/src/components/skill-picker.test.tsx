import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SkillPicker } from "./skill-picker";

const concept = { concept_id: "postgres-id", preferred_label: "PostgreSQL" };
const stored = {
  ...concept,
  vocabulary_version: "test.1",
  created_at: "2026-08-25T00:00:00Z",
};

function response(body: unknown, status = 200): Response {
  return Response.json(body, { status });
}

afterEach(() => vi.unstubAllGlobals());

describe("SkillPicker", () => {
  it("searches concepts and selects by concept id rather than typed text", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response([]))
      .mockResolvedValueOnce(response([concept]))
      .mockResolvedValueOnce(response(stored, 201));
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();

    render(<SkillPicker />);
    await user.type(await screen.findByLabelText("Search canonical skills"), "Postgres typed text");
    await user.click(screen.getByRole("button", { name: "Search" }));
    await user.click(await screen.findByRole("button", { name: "Add PostgreSQL" }));

    expect(await screen.findByLabelText("Selected skills")).toHaveTextContent("PostgreSQL");
    expect(fetch).toHaveBeenNthCalledWith(
      3,
      "/api/profile/skills",
      expect.objectContaining({
        body: JSON.stringify({ concept_id: "postgres-id" }),
      }),
    );
  });

  it("visibly refuses a search with no match and offers no typed-text selection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValueOnce(response([])).mockResolvedValueOnce(response([])),
    );
    const user = userEvent.setup();

    render(<SkillPicker />);
    await user.type(await screen.findByLabelText("Search canonical skills"), "Quantum widgets");
    await user.click(screen.getByRole("button", { name: "Search" }));

    expect(await screen.findByText(/No canonical skills match/)).toHaveTextContent(
      "No canonical skills match “Quantum widgets”. The typed text cannot be saved.",
    );
    expect(screen.queryByRole("button", { name: /^Add / })).not.toBeInTheDocument();
  });

  it("renders preferred labels as removable selected entries", async () => {
    const fetch = vi
      .fn()
      .mockResolvedValueOnce(response([stored]))
      .mockResolvedValueOnce(new Response(null, { status: 204 }));
    vi.stubGlobal("fetch", fetch);
    const user = userEvent.setup();

    render(<SkillPicker />);
    await user.click(await screen.findByRole("button", { name: "Remove PostgreSQL" }));

    await waitFor(() => expect(screen.getByText("No skills selected yet.")).toBeVisible());
    expect(fetch).toHaveBeenLastCalledWith(
      "/api/profile/skills/postgres-id",
      expect.objectContaining({ method: "DELETE" }),
    );
  });
});
