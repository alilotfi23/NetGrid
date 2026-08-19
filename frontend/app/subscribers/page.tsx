import Link from "next/link";

import { Nav } from "@/components/nav";
import { loadPlans, loadSubscribers } from "@/lib/api";

// Live dashboard data with a runtime token: never prerender a cached snapshot.
export const dynamic = "force-dynamic";

function statusBadge(status: string) {
  const styles: Record<string, string> = {
    active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
    suspended: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
    expired: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
  };
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
        styles[status] ?? "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
      }`}
    >
      {status}
    </span>
  );
}

export default async function SubscribersPage() {
  const subs = await loadSubscribers();
  const plans = await loadPlans();
  const planNames = new Map(plans.ok ? plans.plans.map((p) => [p.id, p.name]) : []);

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <Nav />
      <div className="mt-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Subscribers
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Subscriber accounts, status, and plan assignments.
        </p>

        {!subs.ok ? (
          <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            Couldn&apos;t load subscribers: {subs.error}. Set <code>NETGRID_DEMO_TOKEN</code> (see
            the frontend README) and ensure the backend is reachable.
          </p>
        ) : subs.subscribers.length === 0 ? (
          <p className="mt-6 text-sm text-zinc-500 dark:text-zinc-400">No subscribers yet.</p>
        ) : (
          <div className="mt-6 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
            <table className="w-full text-left text-sm">
              <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
                <tr>
                  <th className="px-4 py-3 font-medium">Username</th>
                  <th className="px-4 py-3 font-medium">Full name</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Plan</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                {subs.subscribers.map((s) => (
                  <tr key={s.id} className="bg-white hover:bg-zinc-50 dark:bg-zinc-950 dark:hover:bg-zinc-900">
                    <td className="px-4 py-3">
                      <Link
                        href={`/subscribers/${s.id}`}
                        className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                      >
                        {s.username}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">{s.full_name}</td>
                    <td className="px-4 py-3">{statusBadge(s.status)}</td>
                    <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                      {s.plan_id != null ? (planNames.get(s.plan_id) ?? `Plan #${s.plan_id}`) : "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </main>
  );
}
