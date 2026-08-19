import Link from "next/link";
import { notFound } from "next/navigation";

import { Nav } from "@/components/nav";
import { SubscriberForm } from "@/components/subscriber-form";
import { loadPlans, loadSubscriber } from "@/lib/api";

// Needs the live subscriber + plans — never prerender.
export const dynamic = "force-dynamic";

export default async function EditSubscriberPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const subscriberId = Number(id);
  const [subscriber, plans] = await Promise.all([loadSubscriber(subscriberId), loadPlans()]);

  if (!subscriber.ok) {
    if (subscriber.error.includes("not found")) {
      notFound();
    }
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-10">
        <Nav />
        <p className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Couldn&apos;t load subscriber: {subscriber.error}
        </p>
      </main>
    );
  }

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <Nav />
      <div className="mt-8 max-w-2xl">
        <Link
          href={`/subscribers/${subscriberId}`}
          className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
        >
          ← {subscriber.subscriber.full_name}
        </Link>
        <h1 className="mt-2 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Edit subscriber
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Username is immutable; changing status or plan re-syncs the RADIUS
          rows (Auth-Type Reject / radusergroup).
        </p>

        {!plans.ok ? (
          <p className="mt-6 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
            Couldn&apos;t load plans: {plans.error}
          </p>
        ) : (
          <div className="mt-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
            <SubscriberForm subscriber={subscriber.subscriber} plans={plans.plans} />
          </div>
        )}
      </div>
    </main>
  );
}
