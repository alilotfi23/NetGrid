import Link from "next/link";
import { notFound } from "next/navigation";

import { Nav } from "@/components/nav";
import { PaymentForm } from "@/components/payment-form";
import { loadInvoice } from "@/lib/api";
import { formatCurrency, formatDate, formatDay } from "@/lib/format";
import { methodLabel } from "@/components/revenue-report-view";

const statusStyles: Record<string, string> = {
  issued: "bg-sky-100 text-sky-700 dark:bg-sky-950 dark:text-sky-300",
  paid: "bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  overdue: "bg-rose-100 text-rose-700 dark:bg-rose-950 dark:text-rose-300",
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

function kindBadge(kind: string) {
  if (kind !== "overage") return null;
  return (
    <span className="inline-block rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium uppercase tracking-wide text-amber-700 dark:bg-amber-950 dark:text-amber-300">
      Usage surcharge
    </span>
  );
}

export default async function InvoiceDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const invoiceId = Number(id);
  const result = await loadInvoice(invoiceId);

  if (!result.ok) {
    if (result.error.includes("not found")) {
      notFound();
    }
    return (
      <main className="mx-auto w-full max-w-5xl px-6 py-10">
        <Nav />
        <p className="mt-8 rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300">
          Couldn&apos;t load invoice: {result.error}
        </p>
      </main>
    );
  }

  const invoice = result.invoice;
  const paidTotal = invoice.payments.reduce((sum, p) => sum + Number(p.amount), 0);

  return (
    <main className="mx-auto w-full max-w-5xl px-6 py-10">
      <Nav />
      <div className="mt-8">
        <Link
          href="/invoices"
          className="text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-50"
        >
          ← All invoices
        </Link>
        <div className="mt-2 flex items-center gap-3">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Invoice #{invoice.id}
          </h1>
          {statusBadge(invoice.status)}
          {kindBadge(invoice.kind)}
        </div>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          {invoice.plan_name} · {formatDay(invoice.period_start)} –{" "}
          {formatDay(invoice.period_end)}
        </p>

        <dl className="mt-6 grid max-w-2xl grid-cols-1 gap-x-8 gap-y-4 rounded-lg border border-zinc-200 bg-white p-6 text-sm dark:border-zinc-800 dark:bg-zinc-950 sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Subscriber
            </dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">
              {invoice.subscriber_username == null ? (
                `#${invoice.subscriber_id}`
              ) : (
                <Link
                  href={`/subscribers/${invoice.subscriber_id}`}
                  className="text-indigo-600 hover:underline dark:text-indigo-400"
                >
                  {invoice.subscriber_username}
                </Link>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Plan
            </dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">{invoice.plan_name}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Amount
            </dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">
              {formatCurrency(invoice.amount)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Due
            </dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">{formatDay(invoice.due_at)}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Issued
            </dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">
              {formatDate(invoice.issued_at)}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-zinc-500 dark:text-zinc-400">
              Paid
            </dt>
            <dd className="mt-1 text-zinc-900 dark:text-zinc-50">
              {invoice.paid_at ? formatDate(invoice.paid_at) : "—"}
            </dd>
          </div>
        </dl>

        <section className="mt-10">
          <div className="flex items-baseline justify-between">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-50">Payments</h2>
            <span className="text-sm text-zinc-500 dark:text-zinc-400">
              {formatCurrency(paidTotal)} of {formatCurrency(invoice.amount)} paid
            </span>
          </div>

          {invoice.payments.length === 0 ? (
            <p className="mt-3 text-sm text-zinc-500 dark:text-zinc-400">
              No payments recorded yet.
            </p>
          ) : (
            <div className="mt-4 overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-800">
              <table className="w-full text-left text-sm">
                <thead className="border-b border-zinc-200 bg-zinc-50 text-xs uppercase tracking-wide text-zinc-500 dark:border-zinc-800 dark:bg-zinc-900 dark:text-zinc-400">
                  <tr>
                    <th className="px-4 py-3 font-medium">Recorded</th>
                    <th className="px-4 py-3 font-medium">Method</th>
                    <th className="px-4 py-3 font-medium">Reference</th>
                    <th className="px-4 py-3 font-medium">Status</th>
                    <th className="px-4 py-3 text-right font-medium">Amount</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
                  {invoice.payments.map((payment) => (
                    <tr key={payment.id} className="bg-white dark:bg-zinc-950">
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {formatDate(payment.created_at)}
                      </td>
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {methodLabel(payment.method)}
                      </td>
                      <td className="px-4 py-3 text-zinc-700 dark:text-zinc-300">
                        {payment.reference ?? "—"}
                      </td>
                      <td className="px-4 py-3 capitalize text-zinc-700 dark:text-zinc-300">
                        {payment.status}
                      </td>
                      <td className="px-4 py-3 text-right tabular-nums text-zinc-900 dark:text-zinc-50">
                        {formatCurrency(payment.amount)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {invoice.status === "paid" ? (
            <p className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300">
              This invoice is paid in full.
            </p>
          ) : (
            <div className="mt-6 rounded-lg border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-950">
              <h3 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Record a payment
              </h3>
              <div className="mt-4 max-w-xl">
                <PaymentForm invoice={invoice} />
              </div>
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
