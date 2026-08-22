import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import JobsError from "./error";

describe("JobsError", () => {
  it("explains the failure and offers a way out", async () => {
    const reset = vi.fn();
    render(<JobsError error={new Error("connect ECONNREFUSED 10.0.0.4:8000")} reset={reset} />);

    expect(screen.getByRole("heading")).toHaveTextContent("Jobs are unavailable");
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(reset).toHaveBeenCalledOnce();
  });

  it("never shows the underlying message", () => {
    // It comes from the server and can name internal hosts, and a reader can
    // do nothing with it either way.
    const { container } = render(
      <JobsError error={new Error("connect ECONNREFUSED 10.0.0.4:8000")} reset={vi.fn()} />,
    );

    expect(container.textContent).not.toContain("10.0.0.4");
    expect(container.textContent).not.toContain("ECONNREFUSED");
  });
});
