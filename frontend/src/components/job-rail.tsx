import Link from "next/link";

import type { JobSummary } from "@/lib/api/types";
import { workplaceLabel } from "@/lib/format";

/**
 * Real postings from the catalogue, in a rail that scrolls sideways.
 *
 * A trackpad, a touch, or the keyboard moving focus from one card to the next
 * all scroll it, and every one of those is the browser's own behaviour -- so
 * the rail keeps working with scripting turned off, which the catalogue is
 * tested to do.
 */
export function JobRail({ jobs }: { jobs: JobSummary[] }) {
  if (jobs.length === 0) return null;

  return (
    <ul className="rail" aria-label="Recent postings">
      {jobs.map((job) => (
        <li key={job.id} className="w-[17rem] shrink-0 sm:w-[19rem]">
          <Link
            href={`/jobs/${job.id}`}
            className="flex h-full flex-col gap-2 rounded-xl border border-line bg-background p-4 transition-colors hover:border-ink focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
          >
            <span className="font-mono text-[0.7rem] tracking-widest text-ink-soft uppercase">
              {workplaceLabel(job.workplace_type)}
            </span>
            <span className="font-display font-semibold text-ink">{job.title}</span>
            <span className="text-sm text-ink-soft">
              {job.company.display_name}
              {job.location ? ` · ${job.location}` : ""}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
