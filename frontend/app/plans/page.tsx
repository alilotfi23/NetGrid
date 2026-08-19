import Link from "next/link";

import { Nav } from "@/components/nav";
import { loadPlans } from "@/lib/api";

// Live data fetched with a runtime token — never prerender (see app/page.tsx).
export const dynamic = "force-dynamic";

function PlanTable({
  plans,
}: {
  plans: { id: number; name: string; radius_group: string; price: string; duration_days: number; bandwidth_down_mbps: number; bandwidth_up_mbps: number; quota_gb: number | null; is_active: boolean }[];
}) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">Price</th>
            <th className="px-4 py-3 font-medium">Duration</th>
            <th className="px-4 py-3 font-medium">Down / Up</th>
            <th className="px-4 py-3 font-medium">Quota</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {plans.map((plan) => (
            <tr key={plan.id} className="text-zinc-700 dark:text-zinc-300">
              <td className="px-4 py-3">
                <div className="font-medium text-zinc-900 dark:text-zinc-50">{plan.name}</div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">{plan.radius_group}</div>
              </td>
              <td className="px-4 py-3 tabular-nums">{plan.price}</td>
              <td className="px-4 py-3">{plan.duration_days} days</td>
              <td className="px-4 py-3 tabular-nums">
                {plan.bandwidth_down_mbps} / {plan.bandwidth_up_mbps} Mbps
              </td>
              <td className="px-4 py-3 tabular-nums">
                {plan.quota_gb != null ? `${plan.quota_gb} GB` : "—"}
              </td>
              <td className="px-4 py-3">
                <span
                  className={
                    plan.is_active
                      ? "rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                      : "rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                  }
                >
                  {plan.is_active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="px-4 py-3 text-right">
                <Link
                  href={`/plans/${plan.id}/edit`}
                  className="text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  Edit
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function PlansPage() {
  const result = await loadPlans();

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Plans
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Each plan maps to a RADIUS group; bandwidth and quota are pushed
              to FreeRADIUS automatically.
            </p>
          </div>
          <Link
            href="/plans/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
          >
            New plan
          </Link>
        </div>

        {!result.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Plans unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{result.error}</p>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Set NETGRID_DEMO_TOKEN (an admin access token) for the server-side fetch.
            </p>
          </div>
        ) : result.plans.length === 0 ? (
          <p className="rounded-xl border border-zinc-200 bg-white p-5 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
            No plans yet. Create the first one.
          </p>
        ) : (
          <PlanTable plans={result.plans} />
        )}
      </div>
    </main>
  );
}
