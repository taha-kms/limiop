"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { listJobs } from "@/lib/api/client";
import { ApiError } from "@/lib/api/errors";
import type { JobFilters, JobPage, JobSummary } from "@/lib/api/types";

import { JobCard } from "./job-card";

interface JobListProps {
  /** The batch the server already rendered, so the first paint needs no request. */
  initial: JobPage;
  /** The filter set this listing belongs to. A cursor is only valid within it. */
  filters: JobFilters;
}

export function JobList({ initial, filters }: JobListProps) {
  const [jobs, setJobs] = useState<JobSummary[]>(initial.items);
  const [cursor, setCursor] = useState<string | null>(initial.next_cursor);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sentinel = useRef<HTMLDivElement | null>(null);

  // A new filter set is a different listing, so the accumulated batches belong
  // to the previous one and are replaced rather than appended to.
  useEffect(() => {
    setJobs(initial.items);
    setCursor(initial.next_cursor);
    setError(null);
  }, [initial]);

  const loadMore = useCallback(async () => {
    if (cursor === null || loading) return;
    setLoading(true);
    setError(null);
    try {
      const next = await listJobs({ filters, cursor, limit: initial.items.length || undefined });
      // Guard against a batch arriving twice, which would render duplicate keys.
      setJobs((current) => {
        const seen = new Set(current.map((job) => job.id));
        return [...current, ...next.items.filter((job) => !seen.has(job.id))];
      });
      setCursor(next.next_cursor);
    } catch (cause) {
      setError(
        cause instanceof ApiError ? cause.message : "Something went wrong loading more jobs.",
      );
      // The cursor is kept so Try again resumes rather than restarting.
    } finally {
      setLoading(false);
    }
  }, [cursor, filters, initial.items.length, loading]);

  useEffect(() => {
    const target = sentinel.current;
    // No sentinel means the listing is complete; no observer means an
    // environment without one, where the button below is the whole interface.
    if (!target || typeof IntersectionObserver === "undefined") return;

    const observer = new IntersectionObserver((entries) => {
      if (entries.some((entry) => entry.isIntersecting)) void loadMore();
    });
    observer.observe(target);
    return () => observer.disconnect();
  }, [loadMore]);

  if (jobs.length === 0) {
    return (
      <p className="rounded-lg border border-dashed border-slate-300 p-8 text-center text-slate-600 dark:border-slate-700 dark:text-slate-400">
        No jobs match these filters yet. Try widening them.
      </p>
    );
  }

  return (
    <div>
      <ul className="flex flex-col gap-4" aria-label="Job results">
        {jobs.map((job) => (
          <li key={job.id}>
            <JobCard job={job} />
          </li>
        ))}
      </ul>

      {/* Announced politely so a screen reader hears each batch arrive. */}
      <p aria-live="polite" className="sr-only">
        {loading ? "Loading more jobs" : `Showing ${jobs.length} jobs`}
      </p>

      {cursor !== null && (
        <div ref={sentinel} className="mt-6 flex flex-col items-center gap-3">
          {error ? (
            <p role="alert" className="text-sm text-red-700 dark:text-red-400">
              {error}
            </p>
          ) : null}
          {/* Present even with the observer running, so keyboard and
              no-JavaScript-observer users can still reach the next batch. */}
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={loading}
            className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium disabled:opacity-60 dark:border-slate-700"
          >
            {loading ? "Loading…" : error ? "Try again" : "Show more jobs"}
          </button>
        </div>
      )}
    </div>
  );
}
