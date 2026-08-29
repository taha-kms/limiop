import { Suspense } from "react";

import { CountBars } from "@/components/count-bars";
import { MarketFilters } from "@/components/market-filters";
import { getMarketInsights, InsightsUnavailableError } from "@/lib/api/analytics";
import { listSources } from "@/lib/api/client";
import { workplaceLabel } from "@/lib/format";
import { parseInsightsFilters, WINDOW_LABELS, windowStart } from "@/lib/insights-params";

export const metadata = {
  title: "Job market · SkillSync",
  description: "What the collected job catalogue says about the market.",
};

// The catalogue changes hourly, so the numbers are read per request rather
// than at build time.
export const dynamic = "force-dynamic";

const MONTH = new Intl.DateTimeFormat("en", { month: "long", year: "numeric", timeZone: "UTC" });

/** What the numbers on this page are counting, in the page's own words. */
function describe(
  window: Parameters<typeof windowStart>[0],
  source: string | undefined,
  sources: readonly { key: string; display_name: string }[],
): string {
  const period =
    window === "all" ? "over the whole catalogue" : WINDOW_LABELS[window].toLowerCase();
  const board = sources.find((candidate) => candidate.key === source);
  return board ? `${period}, as listed by ${board.display_name}` : period;
}

function Section({
  title,
  note,
  children,
}: {
  title: string;
  note: string;
  children: React.ReactNode;
}) {
  return (
    <section className="flex flex-col gap-3">
      <div>
        <h2 className="font-medium">{title}</h2>
        <p className="text-sm text-slate-600 dark:text-slate-400">{note}</p>
      </div>
      {children}
    </section>
  );
}

export default async function InsightsPage(props: PageProps<"/insights">) {
  // The sources are a filter option, not the figures: failing to read them
  // costs a dropdown, and taking the page down with it would be worse.
  const [raw, sources] = await Promise.all([props.searchParams, listSources().catch(() => [])]);
  const filters = parseInsightsFilters(raw, { sources: sources.map((source) => source.key) });

  let insights;
  try {
    insights = await getMarketInsights({
      since: windowStart(filters.window, new Date()),
      sourceKey: filters.source,
    });
  } catch (cause: unknown) {
    if (!(cause instanceof InsightsUnavailableError)) throw cause;
    return (
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6 sm:p-8">
        <h1 className="text-2xl font-semibold tracking-tight">Job market</h1>
        <section className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
          <h2 className="font-medium">These numbers could not be loaded</h2>
          {/*
            Not zeroes. A market that looks empty and a market nobody could read
            are different answers, and only one of them is about the market.
          */}
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Reload the page to try again.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-8 p-6 sm:p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Job market</h1>
        <p className="text-slate-600 dark:text-slate-400">
          Counted from the jobs SkillSync has collected. Every figure covers postings that are still
          open, {describe(filters.window, filters.source, sources)}.
        </p>
      </header>

      {/* useSearchParams suspends, and the boundary keeps that from holding up
          the figures while the controls resolve. */}
      <Suspense fallback={null}>
        <MarketFilters sources={sources} />
      </Suspense>

      <Section
        title="Most asked-for skills"
        note="Open jobs naming each skill. A job asking for a skill twice counts once."
      >
        <CountBars
          rows={insights.skills.map((skill) => ({
            key: skill.concept_id,
            label: skill.preferred_label,
            jobs: skill.jobs,
          }))}
          unit="jobs"
        />
      </Section>

      <Section
        title="Where the jobs are"
        note="Grouped exactly as the employer wrote it, so two spellings of one city stay two rows."
      >
        <CountBars
          rows={insights.locations.map((row) => ({
            key: row.location,
            label: row.location,
            jobs: row.jobs,
          }))}
          unit="jobs"
        />
      </Section>

      <Section
        title="How the work happens"
        note="Most postings say nothing, and those are counted rather than dropped."
      >
        <CountBars
          rows={insights.workplaceTypes.map((row) => ({
            key: row.workplace_type,
            label:
              row.workplace_type === "unspecified"
                ? "Not stated"
                : workplaceLabel(row.workplace_type),
            jobs: row.jobs,
          }))}
          unit="jobs"
        />
      </Section>

      <Section
        title="Postings over time"
        note="By the month the employer published, in UTC. Undated postings are in no month."
      >
        <CountBars
          rows={insights.trend.map((point) => ({
            key: point.bucket_start,
            label: MONTH.format(new Date(point.bucket_start)),
            jobs: point.jobs,
          }))}
          unit="posted"
        />
      </Section>
    </main>
  );
}
