"use server";

import { type AdminRole, type AdminUserRow, patchAdminUser } from "@/lib/api";

export function patchAdminUserAction(
  userId: string,
  body: { role: AdminRole }
): Promise<AdminUserRow> {
  return patchAdminUser(userId, body);
}
