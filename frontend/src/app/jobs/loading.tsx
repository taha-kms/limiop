export default function LoadingJobs() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 p-6 sm:p-8">
      <p className="sr-only" role="status">
        Loading jobs
      </p>
      {/* Cards rather than a spinner, so the layout does not jump when the
          real results arrive. */}
      {Array.from({ length: 5 }, (_, index) => (
        <div
          key={index}
          className="h-40 animate-pulse rounded-lg border border-slate-200 bg-slate-50 dark:border-slate-800 dark:bg-slate-900"
        />
      ))}
    </main>
  );
}
