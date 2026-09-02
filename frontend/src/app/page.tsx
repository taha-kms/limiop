import Link from "next/link";

import { FitCard } from "@/components/fit-card";
import { JobRail } from "@/components/job-rail";
import { listJobs } from "@/lib/api/client";
import { currentAccount } from "@/lib/api/session";
import type { JobSummary } from "@/lib/api/types";

// The rail shows the live catalogue, so the page is rendered per request.
export const dynamic = "force-dynamic";

const STEPS = [
  {
    heading: "Say what you can do",
    body: "Upload a CV and SkillSync reads the skills it names, or pick them by hand. Both end up in the same place.",
  },
  {
    heading: "Every posting gets ranked",
    body: "SkillSync collects jobs hourly and scores each one against your skills, so the list reorders itself as the catalogue grows.",
  },
  {
    heading: "Apply where you already fit",
    body: "Open a match and you can see which of its skills you have before you spend an evening on the application.",
  },
];

export default async function HomePage() {
  // The catalogue is the page's content, not its reason to exist. Losing it
  // costs a rail; taking the landing page down with it would be worse.
  let recent: JobSummary[] = [];
  try {
    recent = (await listJobs({ limit: 8 })).items;
  } catch {
    // Costs the rail, not the page.
  }

  // Returns null for every reason a request can fail to identify someone, an
  // unreachable API included, so the closer falls back to the anonymous ask.
  const account = await currentAccount();

  return (
    <main className="flex-1">
      <section className="mx-auto grid w-full max-w-5xl gap-10 px-4 py-14 sm:px-6 sm:py-20 lg:grid-cols-[1.1fr_1fr] lg:items-center">
        <div className="flex flex-col gap-6">
          <p className="font-mono text-[0.7rem] tracking-widest text-ink-soft uppercase">
            The catalogue is public · no account needed
          </p>

          <h1 className="font-display text-4xl leading-[1.05] font-semibold tracking-tight text-balance text-ink sm:text-6xl">
            You already have what these jobs want.
          </h1>

          <p className="max-w-prose text-lg text-ink-soft">
            Most job boards ask what you are looking for. SkillSync asks what you can already do,
            then ranks every posting it collects against that.
          </p>

          <div className="flex flex-wrap gap-3">
            <Link href="/jobs" className="primary-button">
              Browse the catalogue
            </Link>
            <Link href="/onboarding" className="secondary-button">
              Build your profile
            </Link>
          </div>
        </div>

        <FitCard />
      </section>

      {recent.length > 0 && (
        <section className="border-y border-line bg-mist py-12">
          <div className="mx-auto w-full max-w-5xl px-4 sm:px-6">
            <div className="mb-5 flex flex-wrap items-baseline justify-between gap-2">
              <h2 className="font-display text-2xl font-semibold tracking-tight text-ink">
                Fresh from the catalogue
              </h2>
              <Link
                href="/jobs"
                className="rounded-md text-sm font-medium text-ink underline-offset-4 hover:underline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink"
              >
                See every posting
              </Link>
            </div>
            <JobRail jobs={recent} />
          </div>
        </section>
      )}

      <section className="mx-auto w-full max-w-5xl px-4 py-14 sm:px-6">
        <h2 className="font-display text-2xl font-semibold tracking-tight text-ink">
          How the matching works
        </h2>
        {/* Ordered, because it is a sequence: nothing can be ranked before
            there are skills to rank it against. Numbered markers would say
            the same thing a second time, in the one colour that is reserved
            for a skill the candidate holds. */}
        <ol aria-label="How the matching works" className="mt-6 grid gap-6 sm:grid-cols-3">
          {STEPS.map((step) => (
            <li key={step.heading} className="flex flex-col gap-2 border-t-2 border-ink pt-4">
              <h3 className="font-display font-semibold text-ink">{step.heading}</h3>
              <p className="text-sm text-ink-soft">{step.body}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="border-t border-line">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-4 px-4 py-10 sm:px-6">
          <p className="font-display text-xl font-semibold tracking-tight text-ink">
            {account
              ? "Your matches are ranked and waiting."
              : "Find out what you already qualify for."}
          </p>
          {account ? (
            <Link href="/matches" className="primary-button">
              See your matches
            </Link>
          ) : (
            <Link href="/register" className="primary-button">
              Create an account
            </Link>
          )}
        </div>
      </section>
    </main>
  );
}
