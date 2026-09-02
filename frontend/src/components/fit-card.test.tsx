import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FitCard } from "./fit-card";

describe("FitCard", () => {
  it("says it is an example rather than the reader's own result", () => {
    render(<FitCard />);

    expect(screen.getByText("What a match looks like")).toBeVisible();
  });

  it("separates the skills held from the ones missing, out loud", () => {
    render(<FitCard />);

    // Colour carries this to everyone who can see it. The suffix is what
    // carries it to a reader who cannot.
    expect(screen.getByText(/Python/)).toHaveTextContent("you have this");
    expect(screen.getByText(/Kubernetes/)).toHaveTextContent("not yet");
  });

  it("counts the fit", () => {
    render(<FitCard />);

    expect(screen.getByText("3 of 5 you already have")).toBeVisible();
  });
});
