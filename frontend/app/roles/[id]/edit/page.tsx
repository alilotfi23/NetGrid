import Link from "next/link";
import { notFound } from "next/navigation";

import { Nav } from "@/components/nav";
import { RoleForm } from "@/components/role-form";
import { loadPermissions, loadRoles } from "@/lib/api";

// Live data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

export default async function EditRolePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const roleId = Number(id);
  const [roles, permissions] = await Promise.all([loadRoles(), loadPermissions()]);

  if (!roles.ok) {
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-10">
        <Nav />
        <p className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Couldn&apos;t load roles: {roles.error}
        </p>
      </main>
    );
  }

  const role = roles.roles.find((r) => r.id === roleId);
  if (!role) {
    notFound();
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <Nav />
      <div className="mt-8 max-w-2xl">
        <Link
          href="/roles"
          className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
        >
          ← All roles
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Edit {role.name}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Rename, describe, or change the permission set. Permission changes
          invalidate every admin holding this role immediately — including you,
          if your own admins:manage access would be stripped.
        </p>

        {!permissions.ok ? (
          <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            Couldn&apos;t load permissions: {permissions.error}. The permission
            set can&apos;t be edited right now.
          </p>
        ) : (
          <div className="mt-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <RoleForm role={role} permissions={permissions.permissions} />
          </div>
        )}
      </div>
    </main>
  );
}
