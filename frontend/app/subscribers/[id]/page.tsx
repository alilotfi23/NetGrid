import Link from "next/link";
import { notFound } from "next/navigation";

import { Nav } from "@/components/nav";
import {
  type SubscriberHistoryEntry,
  loadPlans,
  loadSubscriber,
  loadSubscriberHistory,
  loadSubscriberSessions,
  loadSubscriberUsage,
} from "@/lib/api";
import { formatBytes, formatDate, formatDuration, formatMonth } from "@/lib/format";

const statusStyles: Record<string, string> = {
  active: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  suspended: "bg-amber-100 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  expired: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
};

function statusBadge(status: string) {
  return (
    <span
      className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium capitalize ${
        statusStyles[status] ?? "bg-zinc-100 text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
      }`}
    >
      {status}
    </span>
  );
}

function actionLabel(action: string, meta: SubscriberHistoryEntry["metadata_"]) {
  if (action === "create") return "Subscriber created";
  if (action === "delete") return "Subscriber deleted";
  if (action === "update") {
    const parts: string[] = [];
    if (meta?.status_from && meta?.status_to) {
      return `Status changed: ${meta.status_from} → ${meta.status_to}`;
    }
    if (meta?.fields) {
      for (const f of meta.fields) {
        parts.push(f === "plan_id" ? "plan" : f.replaceAll("_", " "));
      }
    }
    return parts.length ? `Updated ${parts.join(", ")}` : "Subscriber updated";
  }
  return action;
}

export default async function SubscriberProfilePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const subscriberId = Number(id);
  const [sub, history, sessions, plans, usage] = await Promise.all([
    loadSubscriber(subscriberId),
    loadSubscriberHistory(subscriberId),
    loadSubscriberSessions(subscriberId),
    loadPlans(),
    loadSubscriberUsage(subscriberId),
  ]);

  if (!sub.ok) {
    if (sub.error.includes("not found")) {
      notFound();
    }
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-10">
        <Nav />
        <p className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Couldn&apos;t load subscriber: {sub.error}
        </p>
      </main>
    );
  }

  const subscriber = sub.subscriber;
  const planNames = new Map(plans.ok ? plans.plans.map((p) => [p.id, p.name]) : []);
  const planName =
    subscriber.plan_id != null
      ? (planNames.get(subscriber.plan_id) ?? `Plan #${subscriber.plan_id}`)
      : null;

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <Nav />
      <div className="mt-8">
        <Link
          href="/subscribers"
          className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
        >
          ← All subscribers
        </Link>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            {subscriber.full_name}
          </h1>
          {statusBadge(subscriber.status)}
          <Link
            href={`/subscribers/${subscriber.id}/edit`}
            className="ml-auto rounded-lg border border-zinc-300 px-3 py-1.5 text-sm font-medium text-zinc-700 transition-colors hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-900"
          >
            Edit
          </Link>
        </div>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">@{subscriber.username}</p>

        <dl className="mt-6 grid max-w-2xl grid-cols-1 gap-x-8 gap-y-4 rounded-lg border border-zinc-200 bg-white p-6 text-sm dark:border-zinc-800 dark:bg-zinc-950 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Email</dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">{subscriber.email ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Phone</dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">{subscriber.phone ?? "—"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Plan</dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">{planName ?? "No plan"}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Created
            </dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">{formatDate(subscriber.created_at)}</dd>
          </div>
          {subscriber.notes ? (
            <div className="sm:col-span-2">
              <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">Notes</dt>
              <dd className="mt-1 text-zinc-900 dark:text-zinc-50">{subscriber.notes}</dd>
            </div>
          ) : null}
        </dl>

        <section className="mt-10">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Live sessions</h2>
          {!sessions.ok ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              Couldn&apos;t load sessions: {sessions.error}
            </p>
          ) : sessions.sessions.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">No active sessions.</p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
                  <tr>
                    <th className="px-4 py-3 font-medium">Started</th>
                    <th className="px-4 py-3 font-medium">NAS</th>
                    <th className="px-4 py-3 font-medium">Framed IP</th>
                    <th className="px-4 py-3 font-medium">Duration</th>
                    <th className="px-4 py-3 font-medium">Download</th>
                    <th className="px-4 py-3 font-medium">Upload</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                  {sessions.sessions.map((s) => (
                    <tr key={s.id} className="bg-white dark:bg-zinc-950">
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {formatDate(s.acctstarttime)}
                      </td>
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">{s.nasipaddress ?? "—"}</td>
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {s.framedipaddress ?? "—"}
                      </td>
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {formatDuration(s.acctsessiontime)}
                      </td>
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {formatBytes(s.acctinputoctets)}
                      </td>
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {formatBytes(s.acctoutputoctets)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="mt-10">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Usage history</h2>
          {!usage.ok ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              Couldn&apos;t load usage: {usage.error}
            </p>
          ) : (
            <>
              {usage.months[0]?.quota_gb != null && (
                <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                  Plan quota: {usage.months[0].quota_gb} GB per month
                </p>
              )}
              <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
                    <tr>
                      <th className="px-4 py-3 font-medium">Month</th>
                      <th className="px-4 py-3 font-medium">Downloaded</th>
                      <th className="px-4 py-3 font-medium">Uploaded</th>
                      <th className="px-4 py-3 font-medium">Total</th>
                      <th className="px-4 py-3 font-medium">Sessions</th>
                      <th className="px-4 py-3 font-medium">Quota used</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                    {usage.months.map((m) => {
                      const pct = m.pct_used;
                      const width = pct == null ? 0 : Math.min(pct, 100);
                      const barColor =
                        pct == null
                          ? "bg-zinc-300 dark:bg-zinc-700"
                          : pct >= 100
                            ? "bg-red-500"
                            : pct >= 80
                              ? "bg-amber-500"
                              : "bg-emerald-500";
                      return (
                        <tr key={m.month} className="bg-white dark:bg-zinc-950">
                          <td className="px-4 py-3 font-medium text-zinc-900 dark:text-zinc-50">
                            {formatMonth(m.month)}
                          </td>
                          <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                            {formatBytes(m.input_octets)}
                          </td>
                          <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                            {formatBytes(m.output_octets)}
                          </td>
                          <td className="px-4 py-3 font-medium text-zinc-700 dark:text-zinc-300">
                            {formatBytes(m.total_octets)}
                          </td>
                          <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                            {m.session_count}
                          </td>
                          <td className="px-4 py-3">
                            {pct == null ? (
                              <span className="text-zinc-500 dark:text-zinc-400">—</span>
                            ) : (
                              <div className="flex items-center gap-2">
                                <div
                                  role="progressbar"
                                  aria-valuenow={Math.round(width)}
                                  aria-valuemin={0}
                                  aria-valuemax={100}
                                  aria-label={`${m.month} quota used`}
                                  className="h-1.5 w-24 rounded-full bg-zinc-100 dark:bg-zinc-800"
                                >
                                  <div
                                    className={`h-1.5 rounded-full ${barColor}`}
                                    style={{ width: `${width}%` }}
                                  />
                                </div>
                                <span
                                  className={`text-xs tabular-nums ${
                                    pct >= 100
                                      ? "text-red-600 dark:text-red-400"
                                      : "text-zinc-500 dark:text-zinc-400"
                                  }`}
                                >
                                  {pct.toFixed(1)}%
                                </span>
                              </div>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </section>

        <section className="mt-10">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Status history</h2>
          {!history.ok ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              Couldn&apos;t load history: {history.error}
            </p>
          ) : history.history.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">No recorded events.</p>
          ) : (
            <ul className="mt-4 space-y-3">
              {history.history.map((entry) => (
                <li key={entry.id} className="flex items-baseline gap-3 text-sm">
                  <span className="h-2 w-2 shrink-0 translate-y-[-2px] rounded-full bg-indigo-500" />
                  <span className="text-zinc-900 dark:text-zinc-50">
                    {actionLabel(entry.action, entry.metadata_)}
                  </span>
                  <span className="ml-auto whitespace-nowrap text-xs text-zinc-500 dark:text-zinc-400">
                    {formatDate(entry.created_at)}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </main>
  );
}
