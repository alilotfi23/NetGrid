import type { Admin } from "./api";

/**
 * Count how many admins hold each role, keyed by role id. Roles with no
 * holders are absent from the map, so callers can distinguish "no members"
 * from "counts unavailable".
 */
export function countRoleMembers(admins: Admin[]): Map<number, number> {
  const counts = new Map<number, number>();
  for (const admin of admins) {
    for (const role of admin.roles) {
      counts.set(role.id, (counts.get(role.id) ?? 0) + 1);
    }
  }
  return counts;
}
