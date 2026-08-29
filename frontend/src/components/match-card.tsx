import Link from "next/link";

import type { JobMatch, MatchedSkill } from "@/lib/api/matches";

function SkillList({
  skills,
  label,
  tone,
}: {
  skills: MatchedSkill[];
  label: string;
  tone: "matched" | "missing";
}) {
  if (skills.length === 0) return null;
  const style =
    tone === "matched"
      ? "bg-emerald-100 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
      : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300";

  return (
    <div className="mt-3">
      <h3 className="text-xs font-medium text-slate-600 dark:text-slate-400">{label}</h3>
      <ul className="mt-1.5 flex flex-wrap gap-1.5">
        {skills.map((skill) => (
          <li key={skill.concept_id} className={`rounded-full px-2.5 py-0.5 text-xs ${style}`}>
            {skill.preferred_label}
          </li>
        ))}
      </ul>
    </div>
  );
}

export function MatchCard({ match }: { match: JobMatch }) {
  const { job, matched_skills: matched, missing_skills: missing } = match;
  const asked = matched.length + missing.length;

  return (
    <article className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="text-lg font-semibold">
          <Link
            href={`/jobs/${job.id}`}
            className="underline-offset-4 hover:underline focus-visible:underline"
          >
            {job.title}
          </Link>
        </h2>
        {/*
          The count, not only the percentage. "3 of 4 skills" says what the
          number is made of, and a reader can disagree with it.
        */}
        <p className="text-sm font-medium">
          {matched.length} of {asked} skill{asked === 1 ? "" : "s"}
        </p>
      </div>
      <p className="mt-0.5 text-sm text-slate-600 dark:text-slate-400">
        {job.company.display_name}
        {job.location ? ` · ${job.location}` : ""}
      </p>

      <SkillList skills={matched} label="You have" tone="matched" />
      <SkillList skills={missing} label="This role also asks for" tone="missing" />

      <a
        href={job.application_url}
        target="_blank"
        rel="noopener noreferrer nofollow external"
        className="mt-4 inline-block text-sm font-medium text-blue-700 underline underline-offset-2 dark:text-blue-400"
      >
        Apply on the employer&rsquo;s site
        <span className="sr-only"> for {job.title}, opens in a new tab</span>
      </a>
    </article>
  );
}
