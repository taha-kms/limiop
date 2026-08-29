"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

import { EMPLOYMENT_TYPES, WORKPLACE_TYPES, type JobSource } from "@/lib/api/types";
import { employmentLabel, workplaceLabel } from "@/lib/format";

/**
 * Filters submit as a plain GET form.
 *
 * The action posts to the same route, so without JavaScript the browser
 * navigates to the filtered URL on its own and the page still works. With
 * JavaScript the same submission is intercepted and routed, which keeps the
 * scroll position and avoids a full reload.
 *
 * The boards are passed in rather than read here: they are catalogue data, and
 * the page has already read them by the time this renders.
 */
export function JobFilters({ sources = [] }: { sources?: readonly JobSource[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();

  const selected = (key: string) => new Set(params.getAll(key));

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const next = new URLSearchParams();
    for (const [key, value] of form.entries()) {
      // Blank inputs are dropped rather than sent empty: the API refuses an
      // empty value, so "no filter" and "filter for nothing" must not be the
      // same request. No cursor is carried, because this is a new listing.
      if (typeof value === "string" && value.trim()) next.append(key, value.trim());
    }
    const query = next.toString();
    startTransition(() => router.push(query ? `/jobs?${query}` : "/jobs"));
  }

  const workplace = selected("workplace_type");
  const employment = selected("employment_type");

  return (
    <form onSubmit={submit} method="get" action="/jobs" className="flex flex-col gap-4">
      <div className="flex flex-col gap-3 sm:flex-row">
        <label className="flex flex-1 flex-col gap-1 text-sm">
          <span className="font-medium">Search job titles</span>
          <input
            type="search"
            name="q"
            defaultValue={params.get("q") ?? ""}
            placeholder="engineer"
            className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
        <label className="flex flex-1 flex-col gap-1 text-sm">
          <span className="font-medium">Location</span>
          <input
            type="search"
            name="location"
            defaultValue={params.get("location") ?? ""}
            placeholder="Berlin"
            className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          />
        </label>
      </div>

      {sources.length > 0 && (
        <label className="flex flex-col gap-1 text-sm sm:max-w-xs">
          <span className="font-medium">Source</span>
          <select
            name="source"
            defaultValue={params.get("source") ?? ""}
            className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Any source</option>
            {sources.map((source) => (
              <option key={source.key} value={source.key}>
                {source.display_name}
              </option>
            ))}
          </select>
        </label>
      )}

      <fieldset className="flex flex-wrap items-center gap-3">
        <legend className="text-sm font-medium">Workplace</legend>
        {WORKPLACE_TYPES.map((value) => (
          <label key={value} className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              name="workplace_type"
              value={value}
              defaultChecked={workplace.has(value)}
            />
            {workplaceLabel(value)}
          </label>
        ))}
      </fieldset>

      <fieldset className="flex flex-wrap items-center gap-3">
        <legend className="text-sm font-medium">Employment</legend>
        {EMPLOYMENT_TYPES.map((value) => (
          <label key={value} className="flex items-center gap-1.5 text-sm">
            <input
              type="checkbox"
              name="employment_type"
              value={value}
              defaultChecked={employment.has(value)}
            />
            {employmentLabel(value)}
          </label>
        ))}
      </fieldset>

      <div className="flex gap-3">
        <button
          type="submit"
          disabled={pending}
          className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900"
        >
          {pending ? "Applying…" : "Apply filters"}
        </button>
        <Link
          href="/jobs"
          className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium dark:border-slate-700"
        >
          Clear
        </Link>
      </div>
    </form>
  );
}
