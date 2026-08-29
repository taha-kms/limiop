"use client";

import { type FormEvent, useState } from "react";

import { deleteAccount } from "@/lib/api/auth";

/**
 * Deleting an account is irreversible, so it asks twice: once to open the
 * form, and once with the password, which is what the API requires.
 */
export function DeleteAccountForm() {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const field = event.currentTarget.elements.namedItem("password");
    const password = field instanceof HTMLInputElement ? field.value : "";
    if (!password) {
      setProblem("Enter your password to confirm.");
      return;
    }

    setDeleting(true);
    setProblem(null);
    try {
      await deleteAccount(password);
      // Replaced rather than pushed: the pages behind this one were rendered
      // for an account that no longer exists.
      window.location.replace("/");
      return;
    } catch (cause: unknown) {
      setProblem(cause instanceof Error ? cause.message : "That could not be done.");
    }
    setDeleting(false);
  }

  return (
    <section className="rounded-lg border border-red-200 p-5 dark:border-red-900">
      <h2 className="font-medium">Delete your account</h2>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        This removes your profile, the skills on it, and any CV you uploaded. It cannot be undone.
      </p>

      {confirming ? (
        <form onSubmit={submit} className="mt-4 flex flex-col gap-3" noValidate>
          <label className="flex flex-col gap-1 text-sm">
            <span className="font-medium">Confirm your password</span>
            <input
              type="password"
              name="password"
              autoComplete="current-password"
              className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            />
          </label>
          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={deleting}
              className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 disabled:opacity-60 dark:border-red-800 dark:text-red-400"
            >
              {deleting ? "Deleting…" : "Delete my account"}
            </button>
            <button
              type="button"
              onClick={() => setConfirming(false)}
              disabled={deleting}
              className="text-sm underline"
            >
              Keep my account
            </button>
          </div>
        </form>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="mt-4 text-sm text-red-700 underline dark:text-red-400"
        >
          Delete account
        </button>
      )}

      {problem ? (
        <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">
          {problem}
        </p>
      ) : null}
    </section>
  );
}
