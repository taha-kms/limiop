"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useTransition } from "react";

import type { JobSource } from "@/lib/api/types";
import { DEFAULT_WINDOW, WINDOW_LABELS, WINDOWS } from "@/lib/insights-params";

/**
 * The window and the source, as a plain GET form.
 *
 * Like the listing's filters: the action posts to the same route, so without
 * JavaScript the browser navigates to the filtered URL on its own.
 */
export function MarketFilters({ sources = [] }: { readonly sources?: readonly JobSource[] }) {
  const router = useRouter();
  const params = useSearchParams();
  const [pending, startTransition] = useTransition();

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = new URLSearchParams();
    for (const [key, value] of new FormData(event.currentTarget).entries()) {
      // A blank value means no filter, and the API refuses an empty one.
      if (typeof value === "string" && value.trim()) next.append(key, value.trim());
    }
    const query = next.toString();
    startTransition(() => router.push(query ? `/insights?${query}` : "/insights"));
  }

  return (
    <form
      onSubmit={submit}
      method="get"
      action="/insights"
      className="flex flex-wrap items-end gap-3"
    >
      <label className="flex flex-col gap-1 text-sm">
        <span className="font-medium">Window</span>
        <select
          name="window"
          defaultValue={params.get("window") ?? DEFAULT_WINDOW}
          className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
        >
          {WINDOWS.map((value) => (
            <option key={value} value={value}>
              {WINDOW_LABELS[value]}
            </option>
          ))}
        </select>
      </label>

      {sources.length > 0 ? (
        <label className="flex flex-col gap-1 text-sm">
          <span className="font-medium">Source</span>
          <select
            name="source"
            defaultValue={params.get("source") ?? ""}
            className="rounded-md border border-slate-300 px-3 py-2 dark:border-slate-700 dark:bg-slate-900"
          >
            <option value="">Every source</option>
            {sources.map((source) => (
              <option key={source.key} value={source.key}>
                {source.display_name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <button type="submit" disabled={pending} className="primary-button">
        {pending ? "Applying…" : "Apply"}
      </button>
      <Link href="/insights" className="self-center text-sm underline">
        Clear
      </Link>
    </form>
  );
}
