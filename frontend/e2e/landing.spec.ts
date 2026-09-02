import { expect, test } from "@playwright/test";

/**
 * The landing page, which is the only page that both states what the product
 * does and shows the live catalogue doing it.
 */

test("the landing page leads with the promise and both ways in", async ({ page }) => {
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText(
    "You already have what these jobs want.",
  );
  await expect(page.getByRole("link", { name: "Browse the catalogue" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Build your profile" })).toBeVisible();
});

test("the rail carries real postings through to their own pages", async ({ page }) => {
  await page.goto("/");

  const rail = page.getByRole("list", { name: "Recent postings" });
  await rail.getByRole("link", { name: /Remote Data Engineer/ }).click();

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Remote Data Engineer");
});

test.describe("without JavaScript", () => {
  test.use({ javaScriptEnabled: false });

  // The rail scrolls with the trackpad, a touch, or focus moving between its
  // cards, all of which the browser does itself. Nothing about it is an
  // enhancement, so nothing about it should need scripting.
  test("the rail still renders and still links", async ({ page }) => {
    await page.goto("/");

    const rail = page.getByRole("list", { name: "Recent postings" });
    await expect(rail.getByRole("link").first()).toBeVisible();
    await expect(rail.getByRole("link", { name: /Remote Data Engineer/ })).toHaveAttribute(
      "href",
      /^\/jobs\//,
    );
  });
});

test("the header marks the section you are on", async ({ page }) => {
  await page.goto("/jobs");

  const header = page.getByRole("navigation", { name: "Main" });
  await expect(header.getByRole("link", { name: "Jobs" })).toHaveAttribute("aria-current", "page");
  await expect(header.getByRole("link", { name: "Job market" })).not.toHaveAttribute(
    "aria-current",
    "page",
  );
});

test.describe("the fit card cycles", () => {
  // Pure keyframes, so the roles are all in the document from the first byte
  // and only which one is painted changes.
  test("carries every role without scripting", async ({ page }) => {
    await page.goto("/");

    const examples = page.getByRole("list", { name: "Example matches" });
    await expect(examples.locator("> li")).toHaveCount(4);
    await expect(examples).toContainText("Data Engineer");
    await expect(examples).toContainText("Platform Engineer");
  });

  test("holds still for a reader who asked it to", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce" });
    const page = await context.newPage();
    await page.goto("/");

    // Frozen on the first card: the rest are painted out rather than cycling.
    const first = page.getByRole("list", { name: "Example matches" }).locator("> li").first();
    await expect(first).toHaveCSS("animation-name", "none");
    await expect(first).toHaveCSS("opacity", "1");
    await context.close();
  });
});
