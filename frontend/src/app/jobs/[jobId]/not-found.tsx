import Link from "next/link";

export default function JobNotFound() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-start gap-4 p-6 sm:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">That job is not here</h1>
      <p className="text-slate-600 dark:text-slate-400">
        The posting may have been removed, or the link may be wrong.
      </p>
      <Link href="/jobs" className="text-blue-700 underline dark:text-blue-400">
        Browse all jobs
      </Link>
    </main>
  );
}
