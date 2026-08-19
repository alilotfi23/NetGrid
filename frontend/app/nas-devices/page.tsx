import Link from "next/link";

import { Nav } from "@/components/nav";
import { NasDeviceDeleteButton } from "@/components/nas-device-delete-button";
import { NasDeviceStatusButton } from "@/components/nas-device-status-button";
import { type NasDevice, loadNasDevices } from "@/lib/api";

// Live data fetched with a runtime token — never prerender (see app/page.tsx).
export const dynamic = "force-dynamic";

function NasDeviceTable({ devices }: { devices: NasDevice[] }) {
  return (
    <div className="overflow-x-auto rounded-xl border border-zinc-200 bg-white shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-zinc-200 text-xs text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <tr>
            <th className="px-4 py-3 font-medium">Name</th>
            <th className="px-4 py-3 font-medium">IP address</th>
            <th className="px-4 py-3 font-medium">Type</th>
            <th className="px-4 py-3 font-medium">Ports</th>
            <th className="px-4 py-3 font-medium">Status</th>
            <th className="px-4 py-3" />
          </tr>
        </thead>
        <tbody className="divide-y divide-zinc-100 dark:divide-zinc-900">
          {devices.map((device) => (
            <tr key={device.id} className="text-zinc-700 dark:text-zinc-300">
              <td className="px-4 py-3">
                <div className="font-medium text-zinc-900 dark:text-zinc-50">{device.name}</div>
                <div className="text-xs text-zinc-500 dark:text-zinc-400">{device.shortname}</div>
              </td>
              <td className="px-4 py-3 tabular-nums">{device.ip_address}</td>
              <td className="px-4 py-3">{device.nas_type}</td>
              <td className="px-4 py-3 tabular-nums">{device.ports ?? "—"}</td>
              <td className="px-4 py-3">
                <span
                  className={
                    device.is_active
                      ? "rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400"
                      : "rounded-full bg-zinc-100 px-2 py-0.5 text-xs font-medium text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400"
                  }
                >
                  {device.is_active ? "Active" : "Inactive"}
                </span>
              </td>
              <td className="px-4 py-3">
                <div className="flex items-center justify-end gap-3">
                  <NasDeviceStatusButton deviceId={device.id} isActive={device.is_active} />
                  <Link
                    href={`/nas-devices/${device.id}/edit`}
                    className="text-indigo-600 hover:underline dark:text-indigo-400"
                  >
                    Edit
                  </Link>
                  <NasDeviceDeleteButton deviceId={device.id} deviceName={device.name} />
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default async function NasDevicesPage({
  searchParams,
}: {
  searchParams: Promise<{ nas_type?: string }>;
}) {
  const { nas_type } = await searchParams;
  const result = await loadNasDevices(nas_type);

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <div className="mb-6 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              NAS Devices
            </h1>
            <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
              Routers and gateways that authenticate against FreeRADIUS. Each
              device mirrors a row in the FreeRADIUS nas table; deactivating one
              makes FreeRADIUS treat it as unknown and reject its requests.
            </p>
          </div>
          <Link
            href="/nas-devices/new"
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-indigo-500"
          >
            New NAS device
          </Link>
        </div>

        {nas_type && (
          <div className="mb-4 flex items-center gap-3 rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm text-indigo-800 dark:border-indigo-900 dark:bg-indigo-950 dark:text-indigo-200">
            <span>
              Showing devices of type{" "}
              <strong className="capitalize">{nas_type}</strong>.
            </span>
            <Link href="/nas-devices" className="font-medium underline">
              Clear filter
            </Link>
          </div>
        )}

        {!result.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              NAS devices unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{result.error}</p>
            <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
              Sign in to the dashboard to refresh the session.
            </p>
          </div>
        ) : result.devices.length === 0 ? (
          <p className="rounded-xl border border-zinc-200 bg-white p-5 text-sm text-zinc-500 shadow-sm dark:border-zinc-800 dark:bg-zinc-950 dark:text-zinc-400">
            No NAS devices yet. Add the first router.
          </p>
        ) : (
          <NasDeviceTable devices={result.devices} />
        )}
      </div>
    </main>
  );
}
