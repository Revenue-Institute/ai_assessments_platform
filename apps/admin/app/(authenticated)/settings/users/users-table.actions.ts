"use server";

import { type AdminRole, type AdminUserRow, patchAdminUser } from "@/lib/api";

// biome-ignore lint/suspicious/useAwait: Server Action -- Next.js requires async
export async function patchAdminUserAction(
  userId: string,
  body: { role: AdminRole }
): Promise<AdminUserRow> {
  return patchAdminUser(userId, body);
}
