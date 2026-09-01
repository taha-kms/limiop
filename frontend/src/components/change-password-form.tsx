"use client";

import { type FormEvent, useState } from "react";

import { changePassword } from "@/lib/api/auth";

/**
 * Replaces the password, and says what else that does.
 *
 * Changing a password ends every other session, which is the reason to change
 * one at all — a password you think is known has sessions behind it. Saying so
 * before the fact is the difference between a security control and a surprise.
 */
export function ChangePasswordForm() {
  const [saving, setSaving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [changed, setChanged] = useState(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const current = valueOf(form, "current");
    const next = valueOf(form, "next");

    if (!current || !next) {
      setProblem("Fill in both fields.");
      return;
    }

    setSaving(true);
    setProblem(null);
    setChanged(false);
    try {
      await changePassword(current, next);
      // The response carried a fresh cookie for this device, so there is
      // nowhere to send the caller: they are still signed in, here.
      form.reset();
      setChanged(true);
    } catch (cause: unknown) {
      setProblem(cause instanceof Error ? cause.message : "That could not be done.");
    }
    setSaving(false);
  }

  return (
    <section className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <h2 className="font-medium">Change your password</h2>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
        Every other device is signed out. This one stays signed in.
      </p>

      <form onSubmit={submit} className="mt-4 flex flex-col gap-3" noValidate>
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Current password</span>
          <input
            type="password"
            name="current"
            autoComplete="current-password"
            className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <div className="flex flex-col gap-1 text-sm">
          {/* The hint sits outside the label deliberately. Inside it, it joins
              the accessible name, and the field stops being called "New
              password" to anything reading the form that way. */}
          <label className="flex flex-col gap-1">
            <span className="font-medium">New password</span>
            <input
              type="password"
              name="next"
              autoComplete="new-password"
              aria-describedby="new-password-floor"
              className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
            />
          </label>
          <span id="new-password-floor" className="text-slate-600 dark:text-slate-400">
            At least 12 characters.
          </span>
        </div>
        <button
          type="submit"
          disabled={saving}
          className="self-start rounded-md border border-slate-300 px-3 py-1.5 text-sm font-medium disabled:cursor-not-allowed disabled:opacity-60 dark:border-slate-700"
        >
          {saving ? "Saving…" : "Change password"}
        </button>
      </form>

      {problem ? (
        <p role="alert" className="mt-3 text-sm text-red-700 dark:text-red-400">
          {problem}
        </p>
      ) : null}
      {changed ? (
        <p role="status" className="mt-3 text-sm text-green-700 dark:text-green-400">
          Password changed. Other devices have been signed out.
        </p>
      ) : null}
    </section>
  );
}

function valueOf(form: HTMLFormElement, name: string): string {
  const field = form.elements.namedItem(name);
  return field instanceof HTMLInputElement ? field.value : "";
}
