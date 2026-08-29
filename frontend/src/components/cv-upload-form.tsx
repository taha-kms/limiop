"use client";

import { type FormEvent, useState } from "react";

import type { StoredCV } from "@/lib/api/cvs";

/** Mirrors the API's own limit so the form can say it before a rejection. */
const MAXIMUM_BYTES = 5 * 1024 * 1024;

/**
 * What the API says when it refuses an upload, said in a way a person can act
 * on. The codes are the policy's own, so a new one shows its raw value rather
 * than being silently rendered as something reassuring.
 */
const REFUSALS: Record<string, string> = {
  invalid_filename: "That filename cannot be used. Rename the file and try again.",
  empty_file: "That file is empty.",
  file_too_large: "That file is over 5 MB. Export it again at a smaller size.",
  unsupported_media_type: "Only PDFs are accepted.",
  unsupported_content: "That file is not a PDF, whatever its name says.",
};

interface Props {
  readonly current: StoredCV | null;
}

export function CVUploadForm({ current }: Props) {
  const [uploading, setUploading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    // Read from the input rather than from the form, and sent as the one field
    // the API expects. Explicit about what leaves the browser, and it does not
    // depend on a form's own serialization of a file input.
    const input = event.currentTarget.elements.namedItem("file");
    const chosen = input instanceof HTMLInputElement ? input.files?.[0] : undefined;
    if (!chosen || chosen.size === 0) {
      // Checked here rather than by the browser. The API is what enforces the
      // policy, and a second copy of the rule in markup is a second place it
      // can drift.
      setProblem("Choose a PDF to upload.");
      return;
    }
    const body = new FormData();
    body.append("file", chosen);

    setUploading(true);
    setProblem(null);
    try {
      const response = await fetch("/api/cv", {
        method: "POST",
        credentials: "same-origin",
        body,
      });
      if (response.status === 201) {
        // A full reload, because the state of the CV is rendered on the server
        // and processing starts the moment the upload returns.
        window.location.reload();
        return;
      }
      const detail: unknown = await response.json().catch(() => null);
      setProblem(refusalMessage(detail));
    } catch {
      setProblem("The upload could not be sent. Check your connection and try again.");
    }
    setUploading(false);
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4" noValidate>
      <div className="flex flex-col gap-1">
        <label htmlFor="cv" className="text-sm font-medium">
          {current ? "Replace your CV" : "Your CV"}
        </label>
        <input
          id="cv"
          name="file"
          type="file"
          accept="application/pdf"
          className="text-sm file:mr-3 file:rounded-md file:border file:border-slate-300 file:px-3 file:py-1.5 file:text-sm dark:file:border-slate-700"
        />
        <p className="text-sm text-slate-600 dark:text-slate-400">
          PDF, up to {Math.round(MAXIMUM_BYTES / (1024 * 1024))} MB. It is read once for the skills
          it names, and replaces whatever a previous CV added.
        </p>
      </div>

      {problem ? (
        <p role="alert" className="text-sm text-red-700 dark:text-red-400">
          {problem}
        </p>
      ) : null}

      <button type="submit" disabled={uploading} className="primary-button">
        {uploading ? "Uploading…" : current ? "Replace CV" : "Upload CV"}
      </button>
    </form>
  );
}

function refusalMessage(detail: unknown): string {
  if (detail && typeof detail === "object" && "detail" in detail) {
    const inner = (detail as { detail: unknown }).detail;
    if (inner && typeof inner === "object" && "code" in inner) {
      const code = String((inner as { code: unknown }).code);
      return REFUSALS[code] ?? `That upload was refused (${code}).`;
    }
  }
  return "That upload was refused.";
}
