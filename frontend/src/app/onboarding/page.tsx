import Link from "next/link";
import { redirect } from "next/navigation";

import { OnboardingForm } from "@/components/onboarding-form";
import { currentAccount } from "@/lib/api/session";

export const metadata = {
  title: "Build your profile · SkillSync",
  description: "Tell SkillSync what kind of work fits you.",
};

export default async function OnboardingPage() {
  // Checked on the server so an anonymous visitor never sees a form whose first
  // request is guaranteed to be refused.
  if (!(await currentAccount())) redirect("/sign-in?next=%2Fonboarding");

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-8 p-6 sm:p-8">
      <Link href="/" className="text-sm text-blue-700 underline dark:text-blue-400">
        ← Home
      </Link>
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Build your candidate profile</h1>
        <p className="text-slate-600 dark:text-slate-400">
          Save each step as you go. You can leave and continue where you stopped.
        </p>
      </header>
      <OnboardingForm />
    </main>
  );
}
