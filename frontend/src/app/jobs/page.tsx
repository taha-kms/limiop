import { Suspense } from "react";

import { JobFilters } from "@/components/job-filters";
import { JobList } from "@/components/job-list";
import { listJobs } from "@/lib/api/client";
import { DEFAULT_PAGE_SIZE } from "@/lib/api/types";
import { parseFilters } from "@/lib/search-params";

export const metadata = {
  title: "Jobs · SkillSync",
  description: "Browse the SkillSync job catalogue.",
};

// The catalogue changes hourly and the page is public, so it is rendered per
// request rather than at build time. Nothing here depends on who is asking.
export const dynamic = "force-dynamic";

export default async function JobsPage(props: PageProps<"/jobs">) {
  // Promises in Next 16. Synchronous access was removed, not deprecated.
  const filters = parseFilters(await props.searchParams);
  const page = await listJobs({ filters, limit: DEFAULT_PAGE_SIZE });

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6 sm:p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Jobs</h1>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          Every posting SkillSync has collected, newest first.
        </p>
      </header>

      {/* useSearchParams suspends, and the boundary keeps that from holding up
          the whole page while the filters resolve. */}
      <Suspense fallback={null}>
        <JobFilters />
      </Suspense>

      <JobList initial={page} filters={filters} />
    </main>
  );
}
