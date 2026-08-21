import type { AuditLogEntry } from "./api";
import { formatCurrency } from "./format";

/** Readable labels for the field names the backend records in audit metadata. */
const FIELD_LABELS: Record<string, string> = {
  full_name: "full name",
  plan_id: "plan",
  ip_address: "IP",
  radius_group: "RADIUS group",
  is_active: "active status",
  bandwidth_down_mbps: "download speed",
  bandwidth_up_mbps: "upload speed",
  quota_gb: "quota",
  duration_days: "duration",
  price: "price",
  password: "password",
  email: "email",
  phone: "phone",
  notes: "notes",
  status: "status",
  secret: "shared secret",
};

function fieldLabel(field: string): string {
  return FIELD_LABELS[field] ?? field;
}

function fieldsOf(meta: Record<string, unknown>): string[] {
  const fields = meta.fields;
  return Array.isArray(fields)
    ? fields.filter((field): field is string => typeof field === "string")
    : [];
}

function str(meta: Record<string, unknown>, key: string): string | undefined {
  const value = meta[key];
  return typeof value === "string" ? value : undefined;
}

/**
 * Turn an audit entry's metadata into one short human-readable line for the
 * activity feed, e.g. "status changed active → suspended", "plan moved from
 * Starter to Pro", "shared secret rotated", "payment $99.99 (card)". Returns
 * null when the metadata has nothing worth stating — the action badge alone
 * carries the entry then.
 */
export function summarizeAuditEntry(entry: AuditLogEntry): string | null {
  const meta = entry.metadata_ ?? {};
  const clauses: string[] = [];

  if (entry.resource === "subscribers" && entry.action === "update") {
    const statusFrom = str(meta, "status_from");
    const statusTo = str(meta, "status_to");
    if (statusFrom && statusTo) {
      clauses.push(`status changed ${statusFrom} → ${statusTo}`);
    } else if (statusTo) {
      clauses.push(`status changed to ${statusTo}`);
    }
    const planFrom = str(meta, "plan_from");
    const planTo = str(meta, "plan_to");
    if (planFrom && planTo) {
      clauses.push(`plan moved from ${planFrom} to ${planTo}`);
    } else if (planTo) {
      clauses.push(`plan moved to ${planTo}`);
    }
  }

  if (clauses.length === 0 && entry.action === "update") {
    const fields = fieldsOf(meta);
    if (fields.length > 0) {
      clauses.push(`updated ${fields.map(fieldLabel).join(", ")}`);
    }
  }

  if (entry.resource === "nas_devices" && entry.action === "rotate_secret") {
    clauses.push("shared secret rotated");
  }
  if (entry.resource === "sessions" && entry.action === "disconnect") {
    const result = str(meta, "result");
    if (result) clauses.push(`result ${result}`);
  }
  if (entry.resource === "invoices" && entry.action === "payment") {
    const amount = str(meta, "amount");
    const method = str(meta, "method");
    if (amount) {
      clauses.push(`payment ${formatCurrency(amount)}${method ? ` (${method})` : ""}`);
    }
  }
  if (entry.resource === "invoices" && entry.action === "generate") {
    const created = meta.created;
    if (typeof created === "number") {
      clauses.push(`${created} invoice${created === 1 ? "" : "s"} created`);
    }
  }
  if (entry.resource === "admins" && entry.action === "assign_roles") {
    const roleIds = meta.role_ids;
    if (Array.isArray(roleIds)) {
      clauses.push(`assigned ${roleIds.length} role${roleIds.length === 1 ? "" : "s"}`);
    }
  }
  if (
    entry.resource === "subscribers" &&
    (entry.action === "create" || entry.action === "delete")
  ) {
    const username = str(meta, "username");
    if (username) clauses.push(`username ${username}`);
  }
  if (
    entry.resource === "nas_devices" &&
    (entry.action === "create" || entry.action === "delete")
  ) {
    const ip = str(meta, "ip_address");
    if (ip) clauses.push(`ip ${ip}`);
  }

  return clauses.length > 0 ? clauses.join(", ") : null;
}
