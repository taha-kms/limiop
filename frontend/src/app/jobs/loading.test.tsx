import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import LoadingJobs from "./loading";

describe("LoadingJobs", () => {
  it("tells a screen reader that results are coming", () => {
    render(<LoadingJobs />);

    expect(screen.getByRole("status")).toHaveTextContent("Loading jobs");
  });
});
