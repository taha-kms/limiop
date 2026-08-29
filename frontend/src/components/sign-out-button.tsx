"use client";

import { useState } from "react";

import { signOut } from "@/lib/api/auth";

/**
 * Signs this device out, not every device.
 *
 * The API distinguishes the two — a password change or a disabled account ends
 * every session by bumping a version claim — and blurring them here would let
 * one tab's sign-out look like it had secured the account everywhere.
 */
export function SignOutButton() {
  const [leaving, setLeaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit() {
    setLeaving(true);
    setProblem(null);
    try {
      await signOut();
      // A full document load. The router cache still holds pages rendered for
      // the session that just ended, and replacing the document discards them
      // rather than leaving Back able to show a signed-in render.
      window.location.replace("/");
    } catch {
      setProblem("Signing out failed. Try again.");
      setLeaving(false);
    }
  }

  return (
    <span className="flex items-center gap-2">
      {problem ? (
        <span role="alert" className="text-sm text-red-700 dark:text-red-400">
          {problem}
        </span>
      ) : null}
      <button
        type="button"
        onClick={submit}
        disabled={leaving}
        className="rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700"
      >
        {leaving ? "Signing out…" : "Sign out"}
      </button>
    </span>
  );
}
