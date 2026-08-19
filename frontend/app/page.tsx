import { StatsCard } from "@/components/stats-card";

// The dashboard shows live counts fetched with a runtime token — never
// prerender it at build time (where the token is absent and the fetch would
// be skipped, causing Next to cache the error state).
export const dynamic = "force-dynamic";

export default function Dashboard() {
  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 p-6 font-sans dark:bg-black">
      <div className="mx-auto w-full max-w-5xl">
        <header className="mb-6 flex items-baseline justify-between">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            NetGrid
          </h1>
          <span className="text-sm text-zinc-500 dark:text-zinc-400">Dashboard</span>
        </header>
        <StatsCard />
      </div>
    </main>
  );
}
