import Link from "next/link";

import { Nav } from "@/components/nav";
import { SessionDisconnectButton } from "@/components/session-disconnect-button";
import { formatBytes, formatDate, formatDuration } from "@/lib/format";
import { type LiveSession, loadSessions } from "@/lib/api";

// Live data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

function SessionTable({ sessions }: { sessions: LiveSession[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Subscriber</th>
            <th className="px-4 py-3 font-medium">NAS</th>
            <th className="px-4 py-3 font-medium">Framed IP</th>
            <th className="px-4 py-3 font-medium">Started</th>
            <th className="px-4 py-3 font-medium">Duration</th>
            <th className="px-4 py-3 font-medium">Download</th>
            <th className="px-4 py-3 font-medium">Upload</th>
            <th className="px-4 py-3 font-medium">Actions</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {sessions.map((s) => (
            <tr key={s.id} className="text-zinc-700 dark:text-zinc-300">
              <td className="px-4 py-3 font-medium text-zinc-900 dark:text-zinc-50">
                {s.username == null ? (
                  "—"
                ) : s.subscriber_id != null ? (
                  <Link
                    href={`/subscribers/${s.subscriber_id}`}
                    className="text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    {s.username}
                  </Link>
                ) : (
                  s.username
                )}
              </td>
              <td className="px-4 py-3">
                {s.nas_shortname ? (
                  <>
                    <div className="font-medium text-zinc-900 dark:text-zinc-50">
                      {s.nas_shortname}
                    </div>
                    <div className="text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
                      {s.nasipaddress}
                    </div>
                  </>
                ) : (
                  <span className="tabular-nums">{s.nasipaddress ?? "—"}</span>
                )}
              </td>
              <td className="px-4 py-3 tabular-nums">{s.framedipaddress ?? "—"}</td>
              <td className="px-4 py-3">{formatDate(s.acctstarttime)}</td>
              <td className="px-4 py-3 tabular-nums">{formatDuration(s.acctsessiontime)}</td>
              <td className="px-4 py-3 tabular-nums">{formatBytes(s.acctinputoctets)}</td>
              <td className="px-4 py-3 tabular-nums">{formatBytes(s.acctoutputoctets)}</td>
              <td className="px-4 py-3">
                <SessionDisconnectButton sessionId={s.id} username={s.username ?? ""} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function SessionsPage() {
  const result = await loadSessions();

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <div className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Live Sessions
          </h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Open radacct sessions across all NAS devices, newest first. A
            session disappears once the NAS sends its Accounting-Stop;
            Disconnect sends an RFC 5176 Disconnect-Request to the NAS to
            terminate a session immediately.
          </p>
        </div>

        {!result.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              Live sessions unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{result.error}</p>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Sign in to the dashboard to refresh the session.
            </p>
          </div>
        ) : result.sessions.length === 0 ? (
          <p className="rounded-xl border border-zinc-200 bg-white p-5 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
            No active sessions right now.
          </p>
        ) : (
          <SessionTable sessions={result.sessions} />
        )}
      </div>
    </main>
  );
}
