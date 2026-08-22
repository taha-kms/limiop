"use client";

export default function JobDetailError({ reset }: { error: Error; reset: () => void }) {
  // The message is not rendered: it comes from a server component, can name
  // internal hosts, and a reader can do nothing with it.
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-start gap-4 p-6 sm:p-8">
      <h1 className="text-2xl font-semibold tracking-tight">This job could not be loaded</h1>
      <p className="text-slate-600 dark:text-slate-400">This is usually temporary.</p>
      <button
        type="button"
        onClick={reset}
        className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white dark:bg-slate-100 dark:text-slate-900"
      >
        Try again
      </button>
    </main>
  );
}
