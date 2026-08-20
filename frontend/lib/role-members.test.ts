import { describe, expect, it } from "vitest";

import type { Admin } from "./api";
import { countRoleMembers } from "./role-members";

const admin = (id: number, roleIds: number[]): Admin => ({
  id,
  username: `admin${id}`,
  email: `admin${id}@netgrid.local`,
  is_active: true,
  roles: roleIds.map((roleId) => ({ id: roleId, name: `role${roleId}`, description: null })),
});

describe("countRoleMembers", () => {
  it("counts admins per role, including admins with multiple roles", () => {
    const admins = [admin(1, [1, 2]), admin(2, [1]), admin(3, [3])];

    expect(countRoleMembers(admins)).toEqual(
      new Map([
        [1, 2],
        [2, 1],
        [3, 1],
      ]),
    );
  });

  it("omits roles with no holders", () => {
    expect(countRoleMembers([admin(1, [2])])).toEqual(new Map([[2, 1]]));
  });

  it("returns an empty map for no admins", () => {
    expect(countRoleMembers([])).toEqual(new Map());
  });
});
