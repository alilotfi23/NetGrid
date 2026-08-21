import { describe, expect, it } from "vitest";

import type { AuditLogEntry } from "./api";
import { summarizeAuditEntry } from "./audit-summary";

function entry(overrides: Partial<AuditLogEntry> = {}): AuditLogEntry {
  return {
    id: 1,
    admin_id: 1,
    admin_username: "superadmin",
    action: "update",
    resource: "subscribers",
    resource_id: "12",
    metadata_: null,
    created_at: "2026-08-21T10:00:00Z",
    ...overrides,
  };
}

describe("summarizeAuditEntry", () => {
  it("summarizes a subscriber status change", () => {
    expect(
      summarizeAuditEntry(
        entry({
          metadata_: {
            username: "bob",
            fields: ["status"],
            status_from: "active",
            status_to: "suspended",
          },
        }),
      ),
    ).toBe("status changed active → suspended");
  });

  it("summarizes a subscriber plan move with plan names", () => {
    expect(
      summarizeAuditEntry(
        entry({
          metadata_: {
            username: "bob",
            fields: ["plan_id"],
            plan_from: "Starter",
            plan_to: "Pro",
          },
        }),
      ),
    ).toBe("plan moved from Starter to Pro");
  });

  it("handles a plan assignment without a previous plan", () => {
    expect(
      summarizeAuditEntry(
        entry({
          metadata_: { username: "bob", fields: ["plan_id"], plan_from: null, plan_to: "Pro" },
        }),
      ),
    ).toBe("plan moved to Pro");
  });

  it("combines a status and plan change into one line", () => {
    expect(
      summarizeAuditEntry(
        entry({
          metadata_: {
            username: "bob",
            fields: ["status", "plan_id"],
            status_from: "active",
            status_to: "suspended",
            plan_from: "Starter",
            plan_to: "Pro",
          },
        }),
      ),
    ).toBe("status changed active → suspended, plan moved from Starter to Pro");
  });

  it("lists readable field names for other updates", () => {
    expect(
      summarizeAuditEntry(
        entry({ resource: "plans", metadata_: { name: "Starter", fields: ["price", "is_active"] } }),
      ),
    ).toBe("updated price, active status");
  });

  it("summarizes resource-specific actions", () => {
    expect(
      summarizeAuditEntry(
        entry({ resource: "nas_devices", action: "rotate_secret", metadata_: { name: "core-r1", fields: ["secret"] } }),
      ),
    ).toBe("shared secret rotated");
    expect(
      summarizeAuditEntry(
        entry({ resource: "sessions", action: "disconnect", metadata_: { result: "ack" } }),
      ),
    ).toBe("result ack");
    expect(
      summarizeAuditEntry(
        entry({ resource: "invoices", action: "payment", metadata_: { amount: "99.99", method: "card" } }),
      ),
    ).toBe("payment $99.99 (card)");
    expect(
      summarizeAuditEntry(
        entry({ resource: "invoices", action: "generate", metadata_: { created: 3 } }),
      ),
    ).toBe("3 invoices created");
    expect(
      summarizeAuditEntry(
        entry({ resource: "admins", action: "assign_roles", metadata_: { role_ids: [1, 2] } }),
      ),
    ).toBe("assigned 2 roles");
  });

  it("includes the username for subscriber create and delete", () => {
    expect(
      summarizeAuditEntry(entry({ action: "create", metadata_: { username: "bob", status: "active" } })),
    ).toBe("username bob");
    expect(
      summarizeAuditEntry(entry({ action: "delete", metadata_: { username: "bob" } })),
    ).toBe("username bob");
  });

  it("returns null when the metadata has nothing worth stating", () => {
    expect(summarizeAuditEntry(entry())).toBeNull();
    expect(summarizeAuditEntry(entry({ action: "login", resource: "auth", metadata_: { ip: "1.2.3.4" } }))).toBeNull();
  });
});
