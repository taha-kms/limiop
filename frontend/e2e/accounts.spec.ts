import { expect, test } from "@playwright/test";

/**
 * Registering, signing in, reaching a personalized page, and signing out.
 *
 * This is the path that made Phase C's exit criterion describe a user who could
 * not exist: identity worked in the API and had no route in the browser. It
 * runs against the built frontend and a real API, so it exercises the session
 * cookie as it is actually set — same-origin, HttpOnly, never in a response
 * body.
 *
 * Each run registers a distinct address, because the database persists across
 * the suite and a second run of a fixed address would collide.
 */
let issued = 0;

function newAddress(): string {
  // example.com, not example.test: the API validates with EmailStr, which
  // refuses reserved and special-use TLDs. The counter matters as much as the
  // clock — two tests in one worker can start inside the same millisecond, and
  // registering an address twice is a 409 rather than a fresh account.
  issued += 1;
  return `candidate-${process.pid}-${Date.now()}-${issued}@example.com`;
}

const PASSWORD = "a-sufficiently-long-password";

test("a visitor can register, sign in, reach their profile, and sign out", async ({ page }) => {
  const email = newAddress();

  await page.goto("/register");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  // Registering signs in, so the header names the account without a second form.
  await expect(page.getByText(email)).toBeVisible();

  // Scoped to the header: the home page says "Build your profile" for the same
  // destination, and a substring match resolves to both.
  await page
    .getByRole("navigation", { name: "Main" })
    .getByRole("link", { name: "Your profile" })
    .click();
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Build your candidate profile");

  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(
    page.getByRole("navigation", { name: "Main" }).getByRole("link", { name: "Sign in" }),
  ).toBeVisible();
  await expect(page.getByText(email)).toBeHidden();
});

test("the session token is never readable by a script", async ({ page }) => {
  const email = newAddress();

  await page.goto("/register");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();
  await expect(page.getByText(email)).toBeVisible();

  // The cookie exists and is HttpOnly, so document.cookie cannot see it. This
  // is the property that lets a server component read the session, which is
  // what keeps a personalized page rendering complete on first byte.
  const session = (await page.context().cookies()).find((cookie) => cookie.name === "session");
  expect(session?.httpOnly).toBe(true);
  expect(await page.evaluate(() => document.cookie)).not.toContain("session=");
});

test("an anonymous visitor asking for the profile is sent to sign in and back again", async ({
  page,
}) => {
  await page.goto("/onboarding");

  await expect(page).toHaveURL(/\/sign-in\?next=%2Fonboarding$/);

  const email = newAddress();
  await page.getByRole("link", { name: "Create one" }).click();
  // Wait for the destination before typing: filling a field that React is
  // about to re-render loses the value, and the form then submits an empty
  // address.
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Create an account");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password").fill(PASSWORD);
  await page.getByRole("button", { name: "Create account" }).click();

  await expect(page).toHaveURL(/\/onboarding$/);
  await expect(page.getByRole("heading", { level: 1 })).toHaveText("Build your candidate profile");
});

test("the catalogue stays public, and applying needs no account", async ({ page }) => {
  await page.goto("/jobs");

  await expect(page.getByRole("link", { name: "Sign in" })).toBeVisible();
  await expect(page.getByRole("link", { name: /Apply on the employer/ }).first()).toBeVisible();
});

test("a rejected sign-in says so without saying which half was wrong", async ({ page }) => {
  await page.goto("/sign-in");
  await page.getByLabel("Email address").fill("nobody@example.com");
  await page.getByLabel("Password").fill("not-the-right-password");
  await page.getByRole("button", { name: "Sign in" }).click();

  // Matched by text: Next mounts a route announcer that is also role="alert".
  await expect(page.getByText("Those credentials were not accepted.")).toBeVisible();
  await expect(page).toHaveURL(/\/sign-in$/);
});
