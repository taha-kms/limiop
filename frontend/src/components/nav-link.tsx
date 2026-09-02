"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

/**
 * A header link that knows whether it is the page you are on.
 *
 * Client-side for `usePathname`, but the current section is real information
 * rather than an enhancement, so it is rendered into the first response and
 * is correct with scripting turned off. `aria-current` carries it to a screen
 * reader; the underline carries it to everybody else.
 */
export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  // Typed as a string, but null wherever no router is mounted. Treating that
  // as "no page is current" keeps the header rendering rather than throwing.
  const pathname = usePathname() as string | null;
  const active = pathname === href || (pathname?.startsWith(`${href}/`) ?? false);

  return (
    <Link
      href={href}
      aria-current={active ? "page" : undefined}
      className={`rounded-md px-2 py-1.5 text-sm transition-colors hover:bg-mist focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-ink ${
        active ? "font-medium text-ink" : "text-ink-soft"
      }`}
    >
      <span
        className={active ? "border-b-2 border-ink pb-0.5" : "border-b-2 border-transparent pb-0.5"}
      >
        {children}
      </span>
    </Link>
  );
}
