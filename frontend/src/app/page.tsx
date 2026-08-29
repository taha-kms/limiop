import Link from "next/link";

export default function HomePage() {
  return (
    <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 p-8">
      <div className="flex flex-col gap-3">
        <h1 className="text-3xl font-semibold tracking-tight">SkillSync</h1>
        <p className="text-slate-600 dark:text-slate-400">
          Find jobs that match the skills you already have.
        </p>
      </div>
      <div className="flex flex-wrap gap-3">
        <Link href="/jobs" className="primary-button">
          Browse the job catalogue
        </Link>
        <Link
          href="/onboarding"
          className="w-fit rounded-md border border-slate-300 px-4 py-2 text-sm font-medium dark:border-slate-700"
        >
          Build your profile
        </Link>
      </div>
      <p className="text-sm text-slate-600 dark:text-slate-400">
        The catalogue is public. An account is only needed for a profile.
      </p>
    </main>
  );
}
