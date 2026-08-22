import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import JobDetailError from "./error";

describe("JobDetailError", () => {
  it("offers a retry", async () => {
    const reset = vi.fn();
    render(<JobDetailError error={new Error("boom")} reset={reset} />);

    await userEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(reset).toHaveBeenCalledOnce();
  });

  it("never shows the underlying message", () => {
    const { container } = render(
      <JobDetailError error={new Error("connect ECONNREFUSED 10.0.0.4:8000")} reset={vi.fn()} />,
    );

    expect(container.textContent).not.toContain("10.0.0.4");
  });
});
