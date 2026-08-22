import type { JobSummary } from "@/lib/api/types";
import { employmentLabel, publishedLabel, workplaceLabel } from "@/lib/format";

function Badge({ children }: { children: React.ReactNode }) {
  return (
    <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-700 dark:bg-slate-800 dark:text-slate-300">
      {children}
    </span>
  );
}

export function JobCard({ job }: { job: JobSummary }) {
  const published = publishedLabel(job.published_at);
  const badges = [
    {
      value: job.workplace_type,
      label: workplaceLabel(job.workplace_type),
      description: "Workplace",
    },
    {
      value: job.employment_type,
      label: employmentLabel(job.employment_type),
      description: "Employment",
    },
  ].filter((badge) => badge.value !== "unspecified");

  return (
    <article className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <h2 className="text-lg font-semibold">{job.title}</h2>
      <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
        {job.company.display_name}
        {job.location ? ` · ${job.location}` : ""}
      </p>

      {/*
        An unstated value gets no badge. Most postings say neither, so showing
        both would put two identical "Not stated" chips on nearly every card,
        with nothing to say which dimension each one meant.
      */}
      {badges.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2" aria-label="Job attributes">
          {badges.map(({ label, description }) => (
            <li key={label}>
              <Badge>
                <span className="sr-only">{description}: </span>
                {label}
              </Badge>
            </li>
          ))}
        </ul>
      )}

      <p className="mt-3 text-sm text-slate-700 dark:text-slate-300">{job.excerpt}</p>

      <div className="mt-4 flex flex-wrap items-center justify-between gap-2">
        {published ? (
          <time
            dateTime={job.published_at ?? undefined}
            className="text-xs text-slate-500 dark:text-slate-500"
          >
            Posted {published}
          </time>
        ) : (
          <span className="text-xs text-slate-500 dark:text-slate-500">No posting date</span>
        )}

        {/*
          The destination is provider-controlled, so the tab is opened without a
          handle back to this one and without passing on any ranking signal.
        */}
        <a
          href={job.application_url}
          target="_blank"
          rel="noopener noreferrer nofollow external"
          className="text-sm font-medium text-blue-700 underline underline-offset-2 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
        >
          Apply on the employer&rsquo;s site
          <span className="sr-only"> for {job.title}, opens in a new tab</span>
        </a>
      </div>
    </article>
  );
}
