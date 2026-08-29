import { describe, expect, it } from "vitest";

import { safeNextPath } from "./next-path";

describe("safeNextPath", () => {
  it("keeps a path on this site", () => {
    expect(safeNextPath("/onboarding")).toBe("/onboarding");
    expect(safeNextPath("/jobs?workplace_type=remote")).toBe("/jobs?workplace_type=remote");
  });

  it.each([
    ["//evil.example/steal", "a scheme-relative URL the browser reads as absolute"],
    ["/\\evil.example/steal", "a backslash form browsers also read as absolute"],
    ["https://evil.example", "an absolute URL"],
    ["javascript:alert(1)", "a script URL"],
    ["onboarding", "a relative path, which could resolve anywhere"],
  ])("refuses %s — %s", (value) => {
    expect(safeNextPath(value)).toBe("/");
  });

  it("refuses anything that is not a single string", () => {
    expect(safeNextPath(undefined)).toBe("/");
    expect(safeNextPath(["/onboarding", "//evil.example"])).toBe("/");
  });
});
