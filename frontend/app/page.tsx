import { Nav } from "@/components/nav";
import { DashboardKpis } from "@/components/dashboard-kpis";
import { NasStatsCard } from "@/components/nas-stats-card";
import { RecentActivityCard } from "@/components/recent-activity-card";
import { RevenueTrendCard } from "@/components/revenue-trend-card";
import { NasTypeBreakdownCard } from "@/components/nas-type-breakdown-card";
import { OverdueAlertCard } from "@/components/overdue-alert-card";
import { SessionsCard } from "@/components/sessions-card";
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
        {/* Headline numbers: active subscribers, live sessions, revenue, overdue. */}
        <div className="mb-6">
          <DashboardKpis />
        </div>
        {/* Trailing-12-month revenue trend, full width under the KPI strip. */}
        <div className="mb-6">
          <RevenueTrendCard />
        </div>
        {/* Surfaces the daily overdue sweep's findings when anything is past due. */}
        <OverdueAlertCard />
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
          <div className="grid grid-cols-1 content-start gap-6">
            <StatsCard />
            {/* Latest audit log entries — hidden for roles without audit_logs:read. */}
            <RecentActivityCard />
          </div>
          <div className="grid grid-cols-1 content-start gap-6">
            <NasStatsCard />
            <NasTypeBreakdownCard />
            <SessionsCard />
          </div>
        </div>
      </div>
    </main>
  );
}
