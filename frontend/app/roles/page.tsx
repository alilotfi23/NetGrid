import Link from "next/link";

import { Nav } from "@/components/nav";
import { RoleDeleteButton } from "@/components/role-delete-button";
import { type Role, loadAdmins, loadRoles } from "@/lib/api";
import { permissionLabel } from "@/lib/format";
import { countRoleMembers } from "@/lib/role-members";

// Live data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

const PERMISSION_CHIPS = 4;

function RoleTable({
  roles,
  memberCounts,
}: {
  roles: Role[];
  /** role id -> admin count; undefined hides the Members column entirely. */
  memberCounts?: Map<number, number>;
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Role</th>
            {memberCounts && <th className="px-4 py-3 font-medium">Members</th>}
            <th className="px-4 py-3 font-medium">Permissions</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {roles.map((role) => (
            <tr key={role.id} className="text-zinc-700 dark:text-zinc-300">
              <td className="px-4 py-3">
                <div className="font-medium text-zinc-900 dark:text-zinc-50">{role.name}</div>
                {role.description && (
                  <div className="text-xs text-zinc-500 dark:text-zinc-400">
                    {role.description}
                  </div>
                )}
              </td>
              {memberCounts && (
                <td className="px-4 py-3 tabular-nums">
                  {memberCounts.get(role.id) ?? 0}
                </td>
              )}
              <td className="px-4 py-3">
                {role.permissions.length === 0 ? (
                  <span className="text-zinc-400 dark:text-zinc-600">No permissions</span>
                ) : (
                  <div className="flex flex-wrap items-center gap-1.5">
                    {role.permissions.slice(0, PERMISSION_CHIPS).map((permission) => (
                      <span
                        key={permission.id}
                        className="rounded-full bg-zinc-100 px-2 py-0.5 font-mono text-xs text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                      >
                        {permissionLabel(permission.code)}
                      </span>
                    ))}
                    {role.permissions.length > PERMISSION_CHIPS && (
                      <span className="text-xs text-zinc-500 dark:text-zinc-400">
                        +{role.permissions.length - PERMISSION_CHIPS} more
                      </span>
                    )}
                  </div>
                )}
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center justify-end gap-3">
                  <Link
                    href={`/roles/${role.id}/edit`}
                    className="text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    Edit
                  </Link>
                  <RoleDeleteButton roleId={role.id} roleName={role.name} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function RolesPage() {
  const [result, admins] = await Promise.all([loadRoles(), loadAdmins()]);
  // member counts need admins:read; without it (or on any error) the Members
  // column is simply hidden — the roles list itself never degrades.
  const memberCounts = admins.ok ? countRoleMembers(admins.admins) : undefined;

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Roles
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Roles bundle permissions into assignable units. Editing a
              role&apos;s permissions revokes affected admins&apos; access
              immediately.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/admins"
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              Admins
            </Link>
            <Link
              href="/roles/new"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
            >
              New role
            </Link>
          </div>
        </div>

        {!result.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Roles unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{result.error}</p>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Sign in to the dashboard to refresh the session.
            </p>
          </div>
        ) : result.roles.length === 0 ? (
          <p className="rounded-xl border border-zinc-200 bg-white p-5 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
            No roles yet. Create the first one.
          </p>
        ) : (
          <RoleTable roles={result.roles} memberCounts={memberCounts} />
        )}
      </div>
    </main>
  );
}
