import Link from "next/link";

import { SignOutButton } from "./sign-out-button";

const links = [
  { href: "/", label: "Dashboard" },
  { href: "/subscribers", label: "Subscribers" },
  { href: "/plans", label: "Plans" },
  { href: "/invoices", label: "Invoices" },
  { href: "/nas-devices", label: "NAS Devices" },
  { href: "/sessions", label: "Sessions" },
  { href: "/admins", label: "Admins" },
  { href: "/audit-logs", label: "Audit Log" },
];

export function Nav() {
  return (
    <header className="border-b border-zinc-200 bg-white dark:border-zinc-800 dark:bg-zinc-950">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-6 py-4">
        <Link href="/" className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          NetGrid
        </Link>
        <nav className="flex items-center gap-5 text-sm">
          {links.map(({ href, label }) => (
            <Link
              key={href}
              href={href}
              className="text-zinc-600 transition-colors hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
            >
              {label}
            </Link>
          ))}
          <SignOutButton />
        </nav>
      </div>
    </header>
  );
}
