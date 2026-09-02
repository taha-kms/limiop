import Link from "next/link";

import { currentAccount } from "@/lib/api/session";

import { NavLink } from "./nav-link";
import { SignOutButton } from "./sign-out-button";

/**
 * The one place the application says who is signed in.
 *
 * A server component, so the HttpOnly session cookie can be read without
 * handing the token to a script and without the header arriving empty and
 * filling in afterwards.
 */
export async function SiteHeader() {
  const account = await currentAccount();

  return (
    <header className="sticky top-0 z-20 border-b border-line bg-background/90 backdrop-blur">
      <nav
        aria-label="Main"
        className="mx-auto flex w-full max-w-5xl flex-wrap items-center gap-x-1 gap-y-2 px-4 py-3 sm:px-6"
      >
        <Link
          href="/"
          className="mr-2 flex items-center gap-2 rounded-md focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
        >
          {/* Two arcs closing on each other: the overlap between what a
              candidate has and what a posting asks for, which is the whole
              of what this product measures. */}
          <span aria-hidden className="flex">
            <span className="h-3.5 w-3.5 rounded-full border-2 border-ink" />
            <span className="-ml-1.5 h-3.5 w-3.5 rounded-full border-2 border-match" />
          </span>
          <span className="font-display text-lg font-semibold tracking-tight text-ink">
            SkillSync
          </span>
        </Link>

        <NavLink href="/jobs">Jobs</NavLink>
        <NavLink href="/insights">Job market</NavLink>

        {account ? (
          <>
            <NavLink href="/matches">Matches</NavLink>
            <NavLink href="/cv">Your CV</NavLink>
            <NavLink href="/onboarding">Your profile</NavLink>

            {/* The account and the way out sit apart from the sections, because
                they act on the account rather than navigating the catalogue. */}
            <span className="ml-auto flex items-center gap-2 pl-2">
              <NavLink href="/account">Account</NavLink>
              <span aria-hidden className="hidden h-4 w-px bg-line sm:block" />
              <span className="hidden max-w-[14rem] truncate text-sm text-ink-soft sm:block">
                {account.email}
              </span>
              <SignOutButton />
            </span>
          </>
        ) : (
          <span className="ml-auto flex items-center gap-2">
            <NavLink href="/sign-in">Sign in</NavLink>
            <Link
              href="/register"
              className="rounded-lg bg-ink px-3.5 py-2 text-sm font-medium text-background transition-colors hover:opacity-90 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
            >
              Create an account
            </Link>
          </span>
        )}
      </nav>
    </header>
  );
}
