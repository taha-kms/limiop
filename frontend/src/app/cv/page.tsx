import Link from "next/link";
import { redirect } from "next/navigation";

import { CVDeleteButton } from "@/components/cv-delete-button";
import { CVUploadForm } from "@/components/cv-upload-form";
import {
  CVUnavailableError,
  type CVProcessingState,
  getStoredCV,
  NotSignedInError,
  type StoredCV,
} from "@/lib/api/cvs";

export const metadata = {
  title: "Your CV · SkillSync",
  description: "Upload a CV and let SkillSync read the skills it names.",
};

/**
 * What each state means to the person who uploaded it, rather than to the
 * pipeline. `pending` and `processing` are one thing from here — the reader
 * cannot act differently on them, and naming both would only invite the
 * question of which is which.
 */
const STATES: Record<CVProcessingState, { title: string; note: string }> = {
  pending: {
    title: "Being read",
    note: "This usually takes a few seconds. Reload the page to check.",
  },
  processing: {
    title: "Being read",
    note: "This usually takes a few seconds. Reload the page to check.",
  },
  processed: {
    title: "Read",
    note: "The skills it named are on your profile. A CV never removes a skill you picked by hand.",
  },
  failed: {
    title: "Could not be read",
    note: "The file may be scanned rather than text, or damaged. Your profile was left as it was — try exporting it again as a text PDF.",
  },
};

function Status({ cv }: { cv: StoredCV }) {
  const state = STATES[cv.processing_state];
  return (
    <section className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
      <h2 className="font-medium">{state.title}</h2>
      <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{state.note}</p>
      <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
        Uploaded {new Date(cv.created_at).toLocaleDateString()} ·{" "}
        {Math.max(1, Math.round(cv.size_bytes / 1024))} KB
      </p>
      <CVDeleteButton cvId={cv.id} />
    </section>
  );
}

export default async function CVPage() {
  let cv: StoredCV | null;
  try {
    cv = await getStoredCV();
  } catch (cause: unknown) {
    if (cause instanceof NotSignedInError) redirect("/sign-in?next=%2Fcv");
    if (!(cause instanceof CVUnavailableError)) throw cause;
    return (
      <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 p-6 sm:p-8">
        <h1 className="text-2xl font-semibold tracking-tight">Your CV</h1>
        <section className="rounded-lg border border-slate-200 p-5 dark:border-slate-800">
          <h2 className="font-medium">Your CV could not be loaded</h2>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Reload the page to try again.
          </p>
        </section>
      </main>
    );
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-6 p-6 sm:p-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Your CV</h1>
        <p className="text-slate-600 dark:text-slate-400">
          SkillSync reads a CV for the skills it names and adds them to your profile. You can also{" "}
          <Link href="/onboarding" className="text-blue-700 underline dark:text-blue-400">
            add skills by hand
          </Link>
          .
        </p>
      </header>

      {cv ? <Status cv={cv} /> : null}
      <CVUploadForm current={cv} />
    </main>
  );
}
