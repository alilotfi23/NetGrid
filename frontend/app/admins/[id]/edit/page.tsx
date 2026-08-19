import Link from "next/link";
import { notFound } from "next/navigation";

import { AdminForm } from "@/components/admin-form";
import { Nav } from "@/components/nav";
import { loadAdmins, loadMe, loadRoles } from "@/lib/api";

// Live data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

export default async function EditAdminPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const adminId = Number(id);
  const [admins, roles, me] = await Promise.all([loadAdmins(), loadRoles(), loadMe()]);

  if (!admins.ok) {
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-10">
        <Nav />
        <p className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Couldn&apos;t load admins: {admins.error}
        </p>
      </main>
    );
  }

  const admin = admins.admins.find((a) => a.id === adminId);
  if (!admin) {
    notFound();
  }

  const isSelf = me.ok && me.me.id === admin.id;

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
          Edit {admin.username}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Change profile fields, reset the password, or adjust role
          assignments. Role changes revoke the account&apos;s outstanding
          tokens immediately.
        </p>

        {!roles.ok ? (
          <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            Couldn&apos;t load roles: {roles.error}. Role assignments can&apos;t
            be edited right now.
          </p>
        ) : (
          <div className="mt-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <AdminForm admin={admin} roles={roles.roles} isSelf={isSelf} />
          </div>
        )}
      </div>
    </main>
  );
}
