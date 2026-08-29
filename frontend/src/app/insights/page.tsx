import { CountBars } from "@/components/count-bars";
import { getMarketInsights, InsightsUnavailableError } from "@/lib/api/analytics";
import { workplaceLabel } from "@/lib/format";

export const metadata = {
  title: "Job market · SkillSync",
  description: "What the collected job catalogue says about the market.",
};

// The catalogue changes hourly, so the numbers are read per request rather
// than at build time.
export const dynamic = "force-dynamic";

const MONTH = new Intl.DateTimeFormat("en", { month: "long", year: "numeric", timeZone: "UTC" });

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

export default async function InsightsPage() {
  let insights;
  try {
    insights = await getMarketInsights();
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
          open.
        </p>
      </header>

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
