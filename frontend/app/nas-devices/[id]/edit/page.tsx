import { Nav } from "@/components/nav";
import { NasDeviceForm } from "@/components/nas-device-form";
import { RotateSecretForm } from "@/components/rotate-secret-form";
import { loadNasDevice } from "@/lib/api";

// Live data fetched with a runtime token — never prerender.
export const dynamic = "force-dynamic";

export default async function EditNasDevicePage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const result = await loadNasDevice(Number(id));

  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-2xl flex-1 px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          {result.ok ? `Edit ${result.device.name}` : "Edit NAS device"}
        </h1>
        <p className="mt-1 mb-6 text-sm text-zinc-500 dark:text-zinc-400">
          The IP address is the device&apos;s RADIUS identity and cannot be
          changed (rename = recreate).
        </p>

        {!result.ok ? (
          <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
            <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
              NAS device unavailable
            </h2>
            <p className="mt-2 text-sm text-red-600 dark:text-red-400">{result.error}</p>
          </div>
        ) : (
          <div className="space-y-6">
            <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
              <NasDeviceForm device={result.device} />
            </div>
            <div className="rounded-xl border border-amber-200 bg-white p-5 shadow-sm dark:border-amber-900 dark:bg-zinc-950">
              <h2 className="text-sm font-semibold text-zinc-900 dark:text-zinc-50">
                Rotate shared secret
              </h2>
              <p className="mb-4 mt-1 text-sm text-zinc-500 dark:text-zinc-400">
                Replaces the encrypted at-rest copy and rewrites the FreeRADIUS
                nas row without touching any other field.
              </p>
              <RotateSecretForm
                deviceId={result.device.id}
                deviceName={result.device.name}
              />
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
