import { Nav } from "@/components/nav";
import { StatsCard } from "@/components/stats-card";

// The dashboard shows live counts fetched with a runtime token — never
// prerender it at build time (where the token is absent and the fetch would
// be skipped, causing Next to cache the error state).
export const dynamic = "force-dynamic";

export default function Dashboard() {
  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-5xl flex-1 px-6 py-8">
        <header className="mb-6">
          <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Dashboard
          </h1>
        </header>
        <StatsCard />
      </div>
    </main>
  );
}
