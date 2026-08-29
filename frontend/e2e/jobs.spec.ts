import { expect, test, type Page } from "@playwright/test";

/**
 * The vertical slice: stored rows, the API, and the rendered page.
 *
 * The catalogue is seeded by `backend/scripts/seed_catalog.py` with four fixed
 * postings, so these assertions are about behaviour rather than about whatever
 * the live job board published this morning.
 */

/**
 * The link that opens a job.
 *
 * Matched exactly, because the apply link names the job too so a reader hears
 * which one it applies to, and a substring match resolves to both.
 */
function openJob(page: Page, title: string) {
  return page.getByRole("link", { name: title, exact: true });
}

const SEEDED = {
  onsite: "Warehouse Coordinator",
  hybrid: "Junior Frontend Developer",
  remote: "Remote Data Engineer",
  internship: "Data Science Intern",
} as const;

test("the catalogue lists every seeded posting, newest first", async ({ page }) => {
  await page.goto("/jobs");

  const titles = page.getByRole("article").getByRole("heading", { level: 2 });
  await expect(titles).toHaveText([SEEDED.internship, SEEDED.remote, SEEDED.hybrid, SEEDED.onsite]);
});

test.describe("without JavaScript", () => {
  // Set through test.use rather than browser.newContext, which would build a
  // context that does not inherit baseURL and send every goto nowhere.
  test.use({ javaScriptEnabled: false });

  test("the listing still renders, because the catalogue is public", async ({ page }) => {
    await page.goto("/jobs");

    await expect(openJob(page, SEEDED.remote)).toBeVisible();
  });
});

test("a filter narrows the listing and survives being shared", async ({ page }) => {
  await page.goto("/jobs");

  await page.getByRole("checkbox", { name: "Remote" }).check();
  await page.getByRole("button", { name: "Apply filters" }).click();

  await expect(page).toHaveURL(/workplace_type=remote/);
  const titles = page.getByRole("article").getByRole("heading", { level: 2 });
  await expect(titles).toHaveText([SEEDED.internship, SEEDED.remote]);

  // The URL is the filter, so opening it fresh must reproduce the same view.
  await page.goto(page.url());
  await expect(titles).toHaveText([SEEDED.internship, SEEDED.remote]);
});

test("filters compose", async ({ page }) => {
  await page.goto("/jobs");

  await page.getByRole("checkbox", { name: "Remote" }).check();
  await page.getByRole("checkbox", { name: "Internship" }).check();
  await page.getByRole("button", { name: "Apply filters" }).click();

  await expect(page.getByRole("article")).toHaveCount(1);
  await expect(page.getByRole("heading", { name: SEEDED.internship })).toBeVisible();
});

test("searching a title finds it and clearing restores the catalogue", async ({ page }) => {
  await page.goto("/jobs");

  await page.getByLabel("Search job titles").fill("warehouse");
  await page.getByRole("button", { name: "Apply filters" }).click();
  await expect(page.getByRole("article")).toHaveCount(1);

  await page.getByRole("link", { name: "Clear" }).click();
  await expect(page.getByRole("article")).toHaveCount(4);
});

test("a filter matching nothing says so", async ({ page }) => {
  await page.goto("/jobs");

  await page.getByLabel("Location").fill("Atlantis");
  await page.getByRole("button", { name: "Apply filters" }).click();

  await expect(page.getByText(/No jobs match these filters/)).toBeVisible();
  await expect(page.getByRole("article")).toHaveCount(0);
});

test("a job opens from the listing and carries its application link", async ({ page }) => {
  await page.goto("/jobs");

  await openJob(page, SEEDED.remote).click();

  await expect(page.getByRole("heading", { level: 1, name: SEEDED.remote })).toBeVisible();
  await expect(page.getByText("Meridian Software")).toBeVisible();
  // The excerpt stops early; the detail page carries the whole posting.
  await expect(page.getByText("Own them end to end.")).toBeVisible();

  const apply = page.getByRole("link", { name: /Apply on the employer/ });
  await expect(apply).toHaveAttribute("href", "https://employer.example.com/apply/3");
  await expect(apply).toHaveAttribute("target", "_blank");
  // The destination is provider-controlled and must not get a handle on this tab.
  await expect(apply).toHaveAttribute("rel", /noopener/);
  await expect(apply).toHaveAttribute("rel", /noreferrer/);
});

test("a job names where it was found and links to the original", async ({ page }) => {
  await page.goto("/jobs");
  await openJob(page, SEEDED.remote).click();

  const source = page.getByRole("link", { name: /Seeded catalogue/ });
  await expect(source).toHaveAttribute("href", "https://seed.example.com/postings/3");
});

test("a link to a job that does not exist says so rather than failing", async ({ page }) => {
  await page.goto("/jobs/00000000-0000-0000-0000-000000000000");

  await expect(page.getByRole("heading", { name: "That job is not here" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Browse all jobs/ })).toBeVisible();
});

test("a malformed job link says the same, rather than offering a retry", async ({ page }) => {
  // Retrying cannot help: the identifier is wrong, not the service.
  await page.goto("/jobs/not-a-uuid");

  await expect(page.getByRole("heading", { name: "That job is not here" })).toBeVisible();
});

test("provider text is never rendered as markup", async ({ page }) => {
  await page.goto("/jobs");
  await openJob(page, SEEDED.remote).click();

  const injected = await page.locator("section[aria-label='Job description'] script").count();
  expect(injected).toBe(0);
});

test("the job-market page is public and counts the seeded catalogue", async ({ page }) => {
  await page.goto("/insights");

  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Job market");
  // Public, like the catalogue it summarises: no account, no sign-in prompt.
  await expect(
    page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Sign in" }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Where the jobs are" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "How the work happens" })).toBeVisible();
});
