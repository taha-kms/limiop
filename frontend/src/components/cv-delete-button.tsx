"use client";

import { useState } from "react";

/**
 * Deleting a CV is not undoable, so it asks once in place.
 *
 * In place rather than through `confirm()`, which is a dialog the page cannot
 * style, cannot test, and which some browsers suppress outright.
 */
export function CVDeleteButton({ cvId }: { readonly cvId: string }) {
  const [confirming, setConfirming] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function remove() {
    setDeleting(true);
    setProblem(null);
    try {
      const response = await fetch(`/api/cv?id=${encodeURIComponent(cvId)}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
      if (response.status === 204) {
        // A full reload, because what a deleted CV leaves behind — no status,
        // a shorter profile — is rendered on the server.
        window.location.reload();
        return;
      }
      setProblem(
        response.status === 404
          ? "That CV is already gone. Reload the page."
          : "Your CV could not be deleted. Try again in a moment.",
      );
    } catch {
      setProblem("Your CV could not be deleted. Check your connection and try again.");
    }
    setDeleting(false);
  }

  return (
    <div className="mt-4 flex flex-col gap-2">
      {confirming ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            This deletes the file and the skills it added. Skills you picked by hand stay.
          </p>
          <button
            type="button"
            onClick={remove}
            disabled={deleting}
            className="rounded-md border border-red-300 px-3 py-1.5 text-sm font-medium text-red-700 disabled:opacity-60 dark:border-red-800 dark:text-red-400"
          >
            {deleting ? "Deleting…" : "Yes, delete it"}
          </button>
          <button
            type="button"
            onClick={() => setConfirming(false)}
            disabled={deleting}
            className="text-sm underline"
          >
            Keep it
          </button>
        </div>
      ) : (
        <button
          type="button"
          onClick={() => setConfirming(true)}
          className="self-start text-sm text-red-700 underline dark:text-red-400"
        >
          Delete CV
        </button>
      )}

      {problem ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {problem}
        </p>
      ) : null}
    </div>
  );
}
