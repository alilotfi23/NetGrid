import { loadNasDevices } from "@/lib/api";
import { NasTypeBreakdownView } from "./nas-type-breakdown-view";

/**
 * Dashboard card for the devices-by-type breakdown. A server component: the
 * by_type field rides on the nas-devices list stats, so it reuses the same
 * fetch as the NAS summary card (deduped by Next within one render).
 */
export async function NasTypeBreakdownCard() {
  const result = await loadNasDevices();
  if (!result.ok) {
    return <NasTypeBreakdownView error={result.error} />;
  }
  return <NasTypeBreakdownView byType={result.stats.by_type} />;
}
