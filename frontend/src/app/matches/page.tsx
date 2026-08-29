import Link from "next/link";
import { redirect } from "next/navigation";

import { MatchCard } from "@/components/match-card";
import { getMatches, MatchesUnavailableError, NotSignedInError } from "@/lib/api/matches";

export const metadata = {
  title: "Your matches · SkillSync",
  description: "Jobs ranked against the skills on your profile.",
};

function Notice({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 p-6 dark:border-slate-800">
      <h2 className="font-medium">{title}</h2>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{children}</p>
    </section>
  );
}

export default async function MatchesPage() {
  let matches;
  try {
    matches = await getMatches();
  } catch (cause: unknown) {
    if (cause instanceof NotSignedInError) redirect("/sign-in?next=%2Fmatches");
    if (cause instanceof MatchesUnavailableError) {
      return (
        <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6 sm:p-8">
          <h1 className="text-2xl font-semibold tracking-tight">Your matches</h1>
          <Notice title="Matches could not be loaded">
            Something went wrong reading your matches. Reload the page to try again.
          </Notice>
        </main>
      );
    }
    throw cause;
  }

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-6 p-6 sm:p-8">
      <header className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">Your matches</h1>
        <p className="text-slate-600 dark:text-slate-400">
          {matches.ranked > 0
            ? `Ranked ${matches.ranked} job${matches.ranked === 1 ? "" : "s"} against the skills on your profile.`
            : "Jobs ranked against the skills on your profile."}
        </p>
      </header>

      {matches.matches.length === 0 ? (
        /*
          One empty state, and it says what to do rather than what happened. The
          API returns nothing both for a profile too thin to rank and for a
          catalogue sharing no skills, and the same next step fixes both.
        */
        <Notice title="No matches yet">
          Matching needs a few skills on your profile to say anything useful.{" "}
          <Link href="/onboarding" className="text-blue-700 underline dark:text-blue-400">
            Add some to your profile
          </Link>{" "}
          and come back.
        </Notice>
      ) : (
        <ul className="flex flex-col gap-4">
          {matches.matches.map((match) => (
            <li key={match.job.id}>
              <MatchCard match={match} />
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
