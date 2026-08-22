import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import JobNotFound from "./not-found";

describe("JobNotFound", () => {
  it("says the job is gone and offers somewhere to go", () => {
    render(<JobNotFound />);

    expect(screen.getByRole("heading")).toHaveTextContent("That job is not here");
    expect(screen.getByRole("link", { name: /Browse all jobs/ })).toHaveAttribute("href", "/jobs");
  });
});
