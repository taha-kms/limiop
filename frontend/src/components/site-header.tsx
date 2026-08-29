import Link from "next/link";

import { currentAccount } from "@/lib/api/session";

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
    <header className="border-b border-slate-200 dark:border-slate-800">
      <nav
        aria-label="Main"
        className="mx-auto flex w-full max-w-3xl flex-wrap items-center justify-between gap-3 p-4"
      >
        <Link href="/" className="font-semibold tracking-tight">
          SkillSync
        </Link>
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <Link href="/jobs" className="underline underline-offset-2">
            Jobs
          </Link>
          {account ? (
            <>
              <Link href="/matches" className="underline underline-offset-2">
                Matches
              </Link>
              <Link href="/onboarding" className="underline underline-offset-2">
                Your profile
              </Link>
              <span className="text-slate-600 dark:text-slate-400">{account.email}</span>
              <SignOutButton />
            </>
          ) : (
            <>
              <Link href="/sign-in" className="underline underline-offset-2">
                Sign in
              </Link>
              <Link
                href="/register"
                className="rounded-md border border-slate-300 px-3 py-1.5 font-medium dark:border-slate-700"
              >
                Create an account
              </Link>
            </>
          )}
        </div>
      </nav>
    </header>
  );
}
