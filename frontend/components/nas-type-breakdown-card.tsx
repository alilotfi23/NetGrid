import { loadNasDevices } from "@/lib/api";
import { NasTypeBreakdownCardClient } from "./nas-type-breakdown-card-client";

/**
 * Dashboard card for the devices-by-type breakdown. A server component: the
 * by_type field rides on the nas-devices list stats, so it reuses the same
 * fetch as the NAS summary card (deduped by Next within one render) and
 * hands it to the polling client as the initial render.
 */
export async function NasTypeBreakdownCard() {
  const initial = await loadNasDevices();
  return <NasTypeBreakdownCardClient initial={initial} />;
}
