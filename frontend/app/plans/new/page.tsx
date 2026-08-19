import { Nav } from "@/components/nav";
import { PlanForm } from "@/components/plan-form";

export default function NewPlanPage() {
  return (
    <main className="flex min-h-screen flex-col bg-zinc-50 font-sans dark:bg-black">
      <Nav />
      <div className="mx-auto w-full max-w-2xl flex-1 px-6 py-8">
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          New plan
        </h1>
        <p className="mt-1 mb-6 text-sm text-zinc-500 dark:text-zinc-400">
          Creating the plan also creates its RADIUS group attribute rows.
        </p>
        <div className="rounded-xl border border-zinc-200 bg-white p-5 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
          <PlanForm />
        </div>
      </div>
    </main>
  );
}
