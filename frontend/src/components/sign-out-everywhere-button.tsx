"use client";

import { useState } from "react";

import { signOutEverywhere } from "@/lib/api/auth";

/**
 * Ends every session, this one included.
 *
 * The header's sign-out clears one cookie and leaves other devices alone. This
 * invalidates the tokens, so a phone left signed in somewhere is refused rather
 * than merely asked to sign in again — which is what somebody reaching for this
 * is asking for.
 */
export function SignOutEverywhereButton() {
  const [leaving, setLeaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit() {
    setLeaving(true);
    setProblem(null);
    try {
      await signOutEverywhere();
      // A full document load, like the header's sign-out: the router cache
      // still holds pages rendered for the session that just ended.
      window.location.replace("/");
    } catch {
      setProblem("That could not be done. Try again.");
      setLeaving(false);
    }
  }

  return (
    <section className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <h2 className="font-medium">Sign out everywhere</h2>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        Ends every session on every device, including this one. Use it if you think somebody else
        has been signed in as you.
      </p>
      <button
        type="button"
        onClick={submit}
        disabled={leaving}
        className="mt-4 rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700"
      >
        {leaving ? "Signing out…" : "Sign out everywhere"}
      </button>
      {problem ? (
        <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">
          {problem}
        </p>
      ) : null}
    </section>
  );
}
