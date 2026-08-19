import Link from "next/link";

import { AdminForm } from "@/components/admin-form";
import { Nav } from "@/components/nav";
import { loadRoles } from "@/lib/api";

// Needs the live roles list for role assignment — never prerender.
export const dynamic = "force-dynamic";

export default async function NewAdminPage() {
  const roles = await loadRoles();

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <Nav />
      <div className="mt-8 max-w-2xl">
        <Link
          href="/admins"
          className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
        >
          ← All admins
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          New admin
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          The password is hashed with argon2 by the backend; it never touches
          the browser. Roles gate which sections the account can access.
        </p>

        {!roles.ok ? (
          <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            Couldn&apos;t load roles: {roles.error}. Roles are needed to assign
            the new admin — refresh and try again.
          </p>
        ) : (
          <div className="mt-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <AdminForm roles={roles.roles} />
          </div>
        )}
      </div>
    </main>
  );
}
