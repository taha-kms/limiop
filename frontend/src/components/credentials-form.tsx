"use client";

import { type FormEvent, useState } from "react";

import { register, signIn } from "@/lib/api/auth";

/** The shortest password the API will accept. Stated so the form can say so. */
const MINIMUM_PASSWORD_LENGTH = 12;

interface Props {
  /** Registering also signs in, so the two differ by one extra call. */
  readonly mode: "sign-in" | "register";
  /** Where to go afterwards. Already validated as a same-site path. */
  readonly next: string;
}

export function CredentialsForm({ mode, next }: Props) {
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const registering = mode === "register";

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const credentials = {
      email: String(form.get("email") ?? ""),
      password: String(form.get("password") ?? ""),
    };

    setSubmitting(true);
    setProblem(null);
    try {
      if (registering) await register(credentials);
      // Registering does not issue a session, so a new account signs in with
      // the credentials it just set rather than being left at the form.
      await signIn(credentials);
      // A full document load, not a client-side navigation. Every page is
      // rendered on the server from the session cookie, and the router cache
      // holds entries built before that cookie existed — including, for anyone
      // arriving from a redirect, an entry for the very page they are being
      // sent back to. Replacing the document is what makes them all agree, and
      // `replace` keeps Back from returning to a form that is now pointless.
      window.location.replace(next);
    } catch (cause: unknown) {
      setProblem(cause instanceof Error ? cause.message : "Something went wrong. Try again.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1">
        <label htmlFor="email" className="text-sm font-medium">
          Email address
        </label>
        <input
          id="email"
          name="email"
          type="email"
          autoComplete="email"
          required
          className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
        />
      </div>

      <div className="flex flex-col gap-1">
        <label htmlFor="password" className="text-sm font-medium">
          Password
        </label>
        <input
          id="password"
          name="password"
          type="password"
          // Naming which of the two this is stops the browser offering to save
          // a password being signed in with, or filling in a new one.
          autoComplete={registering ? "new-password" : "current-password"}
          required
          minLength={registering ? MINIMUM_PASSWORD_LENGTH : undefined}
          // Described by, not labelled by. Folding the hint into the accessible
          // name would have a screen reader read the whole sentence out every
          // time the field takes focus.
          aria-describedby={registering ? "password-hint" : undefined}
          className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
        />
        {registering ? (
          <p id="password-hint" className="text-sm text-slate-600 dark:text-slate-400">
            At least {MINIMUM_PASSWORD_LENGTH} characters. Length is what makes a password hard to
            guess.
          </p>
        ) : null}
      </div>

      {problem ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {problem}
        </p>
      ) : null}

      <button type="submit" disabled={submitting} className="primary-button">
        {submitting
          ? registering
            ? "Creating your account…"
            : "Signing in…"
          : registering
            ? "Create account"
            : "Sign in"}
      </button>
    </form>
  );
}
