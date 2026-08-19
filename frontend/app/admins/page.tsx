import Link from "next/link";

import { AdminDeleteButton } from "@/components/admin-delete-button";
import { AdminStatusButton } from "@/components/admin-status-button";
import { Nav } from "@/components/nav";
import { type Admin, loadAdmins, loadMe } from "@/lib/api";

// Live data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

function AdminTable({ admins, currentAdminId }: { admins: Admin[]; currentAdminId?: number }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Admin</th>
            <th className="px-4 py-3 font-medium">Roles</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {admins.map((admin) => {
            const isSelf = admin.id === currentAdminId;
            return (
              <tr key={admin.id} className="text-zinc-700 dark:text-zinc-300">
                <td className="px-4 py-3">
                  <div className="font-medium text-zinc-900 dark:text-zinc-50">
                    {admin.username}
                    {isSelf && (
                      <span className="ml-2 rounded-full bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300">
                        You
                      </span>
                    )}
                  </div>
                  <div className="text-xs text-zinc-500 dark:text-zinc-400">{admin.email}</div>
                </td>
                <td className="px-4 py-3">
                  {admin.roles.length === 0 ? (
                    <span className="text-zinc-400 dark:text-zinc-600">No roles</span>
                  ) : (
                    <div className="flex flex-wrap gap-1.5">
                      {admin.roles.map((role) => (
                        <span
                          key={role.id}
                          className="rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-700 dark:bg-zinc-800 dark:text-zinc-300"
                        >
                          {role.name}
                        </span>
                      ))}
                    </div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={
                      admin.is_active
                        ? "rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                        : "rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                    }
                  >
                    {admin.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-4 py-3">
                  <div className="flex items-center justify-end gap-3">
                    <AdminStatusButton adminId={admin.id} isActive={admin.is_active} />
                    <Link
                      href={`/admins/${admin.id}/edit`}
                      className="text-indigo-600 hover:underline dark:text-indigo-400"
                    >
                      Edit
                    </Link>
                    {isSelf ? (
                      <span className="cursor-not-allowed text-zinc-400 dark:text-zinc-600">
                        Delete
                      </span>
                    ) : (
                      <AdminDeleteButton adminId={admin.id} adminUsername={admin.username} />
                    )}
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export default async function AdminsPage() {
  const [adminsResult, meResult] = await Promise.all([loadAdmins(), loadMe()]);

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Admins
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Staff accounts with role-based access. Deactivating an admin
              revokes their tokens; role changes take effect immediately via
              the permission cache.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <Link
              href="/roles"
              className="rounded-lg border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
            >
              Roles &amp; permissions
            </Link>
            <Link
              href="/admins/new"
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
            >
              New admin
            </Link>
          </div>
        </div>

        {!adminsResult.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Admins unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{adminsResult.error}</p>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Sign in to the dashboard to refresh the session.
            </p>
          </div>
        ) : adminsResult.admins.length === 0 ? (
          <p className="rounded-xl border border-zinc-200 bg-white p-5 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
            No admin accounts yet. Create the first one.
          </p>
        ) : (
          <AdminTable admins={adminsResult.admins} currentAdminId={meResult.ok ? meResult.me.id : undefined} />
        )}
      </div>
    </main>
  );
}
