import Link from "next/link";
import { redirect } from "next/navigation";

import { CredentialsForm } from "@/components/credentials-form";
import { currentAccount } from "@/lib/api/session";
import { safeNextPath } from "@/lib/next-path";

export const metadata = {
  title: "Create an account · SkillSync",
  description: "Create a SkillSync account to build a candidate profile.",
};

export default async function RegisterPage(props: PageProps<"/register">) {
  const next = safeNextPath((await props.searchParams).next);
  if (await currentAccount()) redirect(next);

  return (
    <main className="mx-auto flex w-full max-w-sm flex-1 flex-col gap-8 p-6 sm:p-8">
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Create an account</h1>
        <p className="text-slate-600 dark:text-slate-400">
          An account holds your candidate profile. The job catalogue stays public either way.
        </p>
      </header>
      <CredentialsForm mode="register" next={next} />
      <p className="text-sm">
        Already have one?{" "}
        <Link
          href={`/sign-in?next=${encodeURIComponent(next)}`}
          className="text-blue-700 underline dark:text-blue-400"
        >
          Sign in
        </Link>
        .
      </p>
    </main>
  );
}
