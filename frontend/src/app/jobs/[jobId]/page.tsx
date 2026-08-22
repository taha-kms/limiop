import Link from "next/link";
import { notFound } from "next/navigation";

import { getJob } from "@/lib/api/client";
import { InvalidRequestError, JobNotFoundError } from "@/lib/api/errors";
import type { JobDetail } from "@/lib/api/types";
import { employmentLabel, publishedLabel, workplaceLabel } from "@/lib/format";

export const dynamic = "force-dynamic";

const STATUS_NOTICE: Record<string, string> = {
  expired: "This posting has expired. The employer may no longer be hiring for it.",
  removed: "This posting was withdrawn. The employer may no longer be hiring for it.",
};

async function read(jobId: string): Promise<JobDetail> {
  try {
    return await getJob(jobId);
  } catch (cause) {
    // A missing job is a not-found page, not a failure.
    //
    // So is an identifier the API refuses to parse. It is the only thing this
    // route sends, so a rejected request means the link is wrong, and offering
    // to try again would invite a reader to retry something that cannot start
    // working. Anything else is a real failure and belongs to the error
    // boundary.
    if (cause instanceof JobNotFoundError || cause instanceof InvalidRequestError) notFound();
    throw cause;
  }
}

export default async function JobDetailPage(props: PageProps<"/jobs/[jobId]">) {
  const { jobId } = await props.params;
  const job = await read(jobId);
  const published = publishedLabel(job.published_at);
  const notice = STATUS_NOTICE[job.status];

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6 sm:p-8">
      <Link href="/jobs" className="text-sm text-blue-700 underline dark:text-blue-400">
        ← All jobs
      </Link>

      {notice ? (
        <p
          role="status"
          className="rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200"
        >
          {notice}
        </p>
      ) : null}

      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{job.title}</h1>
        <p className="text-slate-600 dark:text-slate-400">
          {job.company.display_name}
          {job.location ? ` · ${job.location}` : ""}
        </p>
      </header>

      <dl className="grid grid-cols-2 gap-4 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-slate-500 dark:text-slate-500">Workplace</dt>
          <dd>{workplaceLabel(job.workplace_type)}</dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-500">Employment</dt>
          <dd>{employmentLabel(job.employment_type)}</dd>
        </div>
        <div>
          <dt className="text-slate-500 dark:text-slate-500">Posted</dt>
          <dd>
            {published ? (
              <time dateTime={job.published_at ?? undefined}>{published}</time>
            ) : (
              "Not stated"
            )}
          </dd>
        </div>
      </dl>

      {/*
        Provider text. It is stored flattened and React escapes it here, and
        both have to hold: either alone is one mistake away from a live tag on a
        public page. whitespace-pre-line keeps the paragraph breaks that
        flattening preserved.
      */}
      <section aria-label="Job description" className="whitespace-pre-line leading-relaxed">
        {job.description}
      </section>

      <a
        href={job.application_url}
        target="_blank"
        rel="noopener noreferrer nofollow external"
        className="w-fit rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
      >
        Apply on the employer&rsquo;s site
        <span className="sr-only"> for {job.title}, opens in a new tab</span>
      </a>

      {job.sources.length > 0 ? (
        <footer className="border-t border-slate-200 pt-4 text-sm dark:border-slate-800">
          <h2 className="font-medium">Where this was found</h2>
          <ul className="mt-2 flex flex-col gap-1">
            {job.sources.map((source) => (
              <li key={source.key}>
                <a
                  href={source.url}
                  target="_blank"
                  rel="noopener noreferrer nofollow external"
                  className="text-blue-700 underline dark:text-blue-400"
                >
                  {source.display_name}
                  <span className="sr-only">, original posting, opens in a new tab</span>
                </a>
              </li>
            ))}
          </ul>
        </footer>
      ) : null}
    </main>
  );
}
