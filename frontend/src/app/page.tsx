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
      <Link
        href="/jobs"
        className="w-fit rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
      >
        Browse the job catalogue
      </Link>
    </main>
  );
}
