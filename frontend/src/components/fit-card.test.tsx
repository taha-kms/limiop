import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { FitCard } from "./fit-card";

describe("FitCard", () => {
  it("says it is an example rather than the reader's own result", () => {
    render(<FitCard />);

    expect(screen.getByText("What a match looks like")).toBeVisible();
  });

  it("keeps every role in the document, not only the one being painted", () => {
    // The cycle is a paint. A reader who never sees it still gets all four
    // roles, in order, which is the whole explanation of the product.
    render(<FitCard />);

    for (const title of [
      "Data Engineer",
      "Frontend Developer",
      "Data Analyst",
      "Platform Engineer",
    ]) {
      expect(screen.getByText(title)).toBeInTheDocument();
    }
  });

  it("separates the skills held from the ones missing, out loud", () => {
    render(<FitCard />);

    const engineer = screen.getByRole("list", { name: "Skills Data Engineer asks for" });
    expect(within(engineer).getByText(/Python/)).toHaveTextContent("you have this");
    expect(within(engineer).getByText(/Kubernetes/)).toHaveTextContent("not yet");
  });

  it("counts the fit for each role", () => {
    render(<FitCard />);

    expect(screen.getAllByText("3 of 5 you already have")).toHaveLength(3);
    expect(screen.getByText("3 of 4 you already have")).toBeInTheDocument();
  });

  it("hands each card its place in the cycle", () => {
    // Every card runs one shared animation and is offset by its index. Without
    // the offset they would all arrive at once and only the last would show.
    render(<FitCard />);

    const cards = screen.getByRole("list", { name: "Example matches" }).children;
    expect(cards[0]).toHaveStyle({ "--index": "0" });
    expect(cards[3]).toHaveStyle({ "--index": "3" });
  });
});
