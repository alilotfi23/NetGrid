import Link from "next/link";

import { Nav } from "@/components/nav";
import { SubscribersTable } from "@/components/subscribers-table";
import { loadPlans, loadSubscribers } from "@/lib/api";

// Live dashboard data with a runtime token: never prerender a cached snapshot.
export const dynamic = "force-dynamic";

export default async function SubscribersPage({
  searchParams,
}: {
  searchParams: Promise<{ plan_id?: string; no_plan?: string }>;
}) {
  const params = await searchParams;
  const planId = params.plan_id ? Number(params.plan_id) : undefined;
  const noPlan = params.no_plan === "1";
  const subs = await loadSubscribers({ planId, noPlan });
  const plans = await loadPlans();
  const planNames = new Map(plans.ok ? plans.plans.map((p) => [p.id, p.name]) : []);

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <Nav />
      <div className="mt-8">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Subscribers
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Subscriber accounts, status, and plan assignments.
            </p>
          </div>
          <Link
            href="/subscribers/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
          >
            New subscriber
          </Link>
        </div>

        {(planId != null || noPlan) && (
          <div className="mt-4 flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950 dark:text-indigo-200">
            <span>
              {noPlan ? (
                <>Showing subscribers with no plan.</>
              ) : (
                <>
                  Showing subscribers on{" "}
                  <strong>
                    {planId != null ? (planNames.get(planId) ?? `plan #${planId}`) : ""}
                  </strong>
                  .
                </>
              )}
            </span>
            <Link href="/subscribers" className="font-medium underline">
              Clear filter
            </Link>
          </div>
        )}

        {!subs.ok ? (
          <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            Couldn&apos;t load subscribers: {subs.error}. Sign in to the dashboard to refresh the
            session and ensure the backend is reachable.
          </p>
        ) : (
          <div className="mt-6">
            <SubscribersTable
              subscribers={subs.subscribers}
              planNames={Object.fromEntries(planNames)}
            />
          </div>
        )}
      </div>
    </main>
  );
}
