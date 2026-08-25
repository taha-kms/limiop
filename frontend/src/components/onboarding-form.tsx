"use client";

import { type FormEvent, useEffect, useState } from "react";

import {
  type CandidateProfile,
  type CandidateProfileUpdate,
  type EmploymentPreference,
  getCandidateProfile,
  NotSignedInError,
  type WorkplacePreference,
  updateCandidateProfile,
} from "@/lib/api/profile";

import { SkillPicker } from "./skill-picker";

const WORKPLACES: Array<[WorkplacePreference, string]> = [
  ["remote", "Remote"],
  ["hybrid", "Hybrid"],
  ["onsite", "On-site"],
];
const EMPLOYMENTS: Array<[EmploymentPreference, string]> = [
  ["full-time", "Full-time"],
  ["part-time", "Part-time"],
  ["contract", "Contract"],
  ["internship", "Internship"],
  ["temporary", "Temporary"],
];

function currentStep(profile: CandidateProfile | null): 1 | 2 | 3 | 4 {
  if (!profile?.display_name) return 1;
  if (!profile.location) return 2;
  return profile.profile_complete ? 4 : 3;
}

function checkedValues<T extends string>(form: FormData, name: string): T[] {
  return form.getAll(name).map(String) as T[];
}

export function OnboardingForm() {
  const [profile, setProfile] = useState<CandidateProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [requiresSignIn, setRequiresSignIn] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    getCandidateProfile(controller.signal)
      .then((saved) => {
        if (active) setProfile(saved);
      })
      .catch((cause: unknown) => {
        if (!active) return;
        setRequiresSignIn(cause instanceof NotSignedInError);
        setProblem(
          cause instanceof NotSignedInError
            ? cause.message
            : "Your saved profile could not be loaded. Try again.",
        );
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
  }, []);

  async function save(update: CandidateProfileUpdate) {
    setProblem(null);
    setSubmitting(true);
    try {
      setProfile(await updateCandidateProfile(update));
    } catch (cause) {
      setProblem(
        cause instanceof NotSignedInError
          ? cause.message
          : "That step could not be saved. Your earlier progress is still safe.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  function submitName(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void save({ display_name: String(form.get("display_name") ?? "").trim() });
  }

  function submitLocation(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    void save({ location: String(form.get("location") ?? "").trim() });
  }

  function submitPreferences(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const workplaceTypes = checkedValues<WorkplacePreference>(form, "workplace_types");
    const employmentTypes = checkedValues<EmploymentPreference>(form, "employment_types");
    if (workplaceTypes.length === 0 || employmentTypes.length === 0) {
      setProblem("Choose at least one workplace and one employment preference.");
      return;
    }
    void save({ workplace_types: workplaceTypes, employment_types: employmentTypes });
  }

  if (loading) return <p role="status">Loading your saved progress…</p>;

  if (requiresSignIn) {
    return (
      <p
        role="alert"
        className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
      >
        {problem}
      </p>
    );
  }

  const step = currentStep(profile);
  if (step === 4) {
    return (
      <div className="flex flex-col gap-6">
        <p className="text-sm font-medium text-slate-600 dark:text-slate-400">Step 4 of 4</p>
        <section className="flex flex-col gap-3" aria-labelledby="profile-ready-heading">
          <h2 id="profile-ready-heading" className="text-xl font-semibold">
            Your profile is ready
          </h2>
          <p className="text-slate-600 dark:text-slate-400">
            Your required details and job preferences are saved. You can add or change skills now
            and whenever you return to this profile.
          </p>
        </section>
        <SkillPicker />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <p className="text-sm font-medium text-slate-600 dark:text-slate-400">Step {step} of 4</p>
      {problem ? (
        <p
          role="alert"
          className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {problem}
        </p>
      ) : null}

      {step === 1 ? (
        <form className="flex flex-col gap-4" onSubmit={submitName}>
          <div className="flex flex-col gap-2">
            <label htmlFor="display-name" className="font-medium">
              What should employers call you?
            </label>
            <input
              id="display-name"
              name="display_name"
              required
              maxLength={255}
              autoComplete="name"
              className="rounded-md border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-700"
            />
          </div>
          <button className="primary-button" disabled={submitting}>
            {submitting ? "Saving…" : "Save and continue"}
          </button>
        </form>
      ) : null}

      {step === 2 ? (
        <form className="flex flex-col gap-4" onSubmit={submitLocation}>
          <div className="flex flex-col gap-2">
            <label htmlFor="location" className="font-medium">
              Where are you based?
            </label>
            <input
              id="location"
              name="location"
              required
              maxLength={255}
              autoComplete="address-level2"
              className="rounded-md border border-slate-300 bg-transparent px-3 py-2 dark:border-slate-700"
            />
          </div>
          <button className="primary-button" disabled={submitting}>
            {submitting ? "Saving…" : "Save and continue"}
          </button>
        </form>
      ) : null}

      {step === 3 ? (
        <form className="flex flex-col gap-6" onSubmit={submitPreferences}>
          <fieldset className="flex flex-col gap-2">
            <legend className="font-medium">How would you like to work?</legend>
            {WORKPLACES.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2">
                <input type="checkbox" name="workplace_types" value={value} />
                {label}
              </label>
            ))}
          </fieldset>
          <fieldset className="flex flex-col gap-2">
            <legend className="font-medium">Which employment types suit you?</legend>
            {EMPLOYMENTS.map(([value, label]) => (
              <label key={value} className="flex items-center gap-2">
                <input type="checkbox" name="employment_types" value={value} />
                {label}
              </label>
            ))}
          </fieldset>
          <button className="primary-button" disabled={submitting}>
            {submitting ? "Saving…" : "Save and continue"}
          </button>
        </form>
      ) : null}
    </div>
  );
}
