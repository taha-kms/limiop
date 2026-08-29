import Link from "next/link";
import { redirect } from "next/navigation";

import { CredentialsForm } from "@/components/credentials-form";
import { currentAccount } from "@/lib/api/session";
import { safeNextPath } from "@/lib/next-path";

export const metadata = {
  title: "Sign in · SkillSync",
  description: "Sign in to your SkillSync account.",
};

export default async function SignInPage(props: PageProps<"/sign-in">) {
  const next = safeNextPath((await props.searchParams).next);
  // Someone already signed in has nothing to do here, and leaving the form up
  // invites signing in as a second account without noticing the first.
  if (await currentAccount()) redirect(next);

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col gap-8 p-6 sm:p-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Sign in</h1>
        <p className="text-slate-600 dark:text-slate-400">
          Browsing the catalogue needs no account. Signing in is for your profile.
        </p>
      </header>
      <CredentialsForm mode="sign-in" next={next} />
      <p className="text-sm">
        No account yet?{" "}
        <Link
          href={`/register?next=${encodeURIComponent(next)}`}
          className="text-blue-700 underline dark:text-blue-400"
        >
          Create one
        </Link>
        .
      </p>
    </main>
  );
}
