import Link from "next/link";
import { redirect } from "next/navigation";

import { ChangePasswordForm } from "@/components/change-password-form";
import { DeleteAccountForm } from "@/components/delete-account-form";
import { SignOutEverywhereButton } from "@/components/sign-out-everywhere-button";
import { currentAccount } from "@/lib/api/session";

export const metadata = {
  title: "Your account · SkillSync",
  description: "Change your password, sign out everywhere, or delete your account.",
};

export default async function AccountPage() {
  // Checked on the server, like the profile page, so an anonymous visitor never
  // sees a form whose first request is guaranteed to be refused.
  const account = await currentAccount();
  if (!account) redirect("/sign-in?next=%2Faccount");

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-8 p-6 sm:p-8">
      <Link href="/" className="text-sm text-blue-700 underline dark:text-blue-400">
        ← Home
      </Link>
      <header className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Your account</h1>
        <p className="text-slate-600 dark:text-slate-400">
          Signed in as <span className="font-medium">{account.email}</span>.
        </p>
      </header>
      <ChangePasswordForm />
      <SignOutEverywhereButton />
      <DeleteAccountForm />
    </main>
  );
}
