import { Nav } from "@/components/nav";
import { NasDeviceForm } from "@/components/nas-device-form";

// Static — no data fetch, so it can prerender.
export const dynamic = "auto";

export default function NewNasDevicePage() {
  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-2xl flex-1 px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          New NAS device
        </h1>
        <p className="mt-1 mb-6 text-sm text-zinc-500 dark:text-zinc-400">
          The device is mirrored to the FreeRADIUS nas table on creation, so
          FreeRADIUS will accept its RADIUS requests after the next reload. The
          shared secret is stored encrypted and never shown again.
        </p>
        <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <NasDeviceForm />
        </div>
      </div>
    </main>
  );
}
