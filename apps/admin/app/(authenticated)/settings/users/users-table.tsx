"use client";

import { ApiError } from "@repo/api-client";
import { useState, useTransition } from "react";
import type { AdminRole, AdminUserRow } from "@/lib/api";
import { patchAdminUserAction } from "./users-table.actions";

interface Props {
  currentUserId: string | null;
  users: AdminUserRow[];
}

const ROLE_OPTIONS: AdminRole[] = ["admin", "reviewer", "viewer"];

type RowStatus =
  | { kind: "idle" }
  | { kind: "saving" }
  | { kind: "saved" }
  | { kind: "error"; message: string };

interface RowState {
  pendingRole: AdminRole;
  savedRole: AdminRole;
  status: RowStatus;
}

export function UsersTable({ currentUserId, users }: Props) {
  const [rows, setRows] = useState<Record<string, RowState>>(() =>
    Object.fromEntries(
      users.map((u) => [
        u.id,
        {
          pendingRole: u.role,
          savedRole: u.role,
          status: { kind: "idle" } as RowStatus,
        },
      ])
    )
  );
  const [pending, startTransition] = useTransition();

  if (users.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No internal users mirrored in <code>public.users</code> yet.
      </p>
    );
  }

  function setRow(id: string, partial: Partial<RowState>) {
    setRows((prev) => {
      const current = prev[id];
      if (!current) {
        return prev;
      }
      return { ...prev, [id]: { ...current, ...partial } };
    });
  }

  function save(user: AdminUserRow) {
    const state = rows[user.id];
    if (!state) {
      return;
    }
    if (state.pendingRole === state.savedRole) {
      return;
    }
    setRow(user.id, { status: { kind: "saving" } });
    startTransition(async () => {
      try {
        const updated = await patchAdminUserAction(user.id, {
          role: state.pendingRole,
        });
        setRow(user.id, {
          savedRole: updated.role,
          pendingRole: updated.role,
          status: { kind: "saved" },
        });
      } catch (e) {
        setRow(user.id, {
          status: {
            kind: "error",
            message:
              e instanceof ApiError ? e.message : "Failed to update role.",
          },
        });
      }
    });
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground text-xs uppercase">
          <tr>
            <th className="px-2 py-1.5" scope="col">
              Name
            </th>
            <th className="px-2 py-1.5" scope="col">
              Email
            </th>
            <th className="px-2 py-1.5" scope="col">
              Role
            </th>
            <th className="px-2 py-1.5" scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          {users.map((u) => {
            const state = rows[u.id];
            if (!state) {
              return null;
            }
            const isSelf = currentUserId === u.id;
            // Match the server-side refuse rule: an admin can't demote
            // themselves out of admin via this UI. Other edits to self (e.g.
            // viewer to viewer, no change) just stay disabled until dirty.
            const selfDemotion =
              isSelf &&
              state.savedRole === "admin" &&
              state.pendingRole !== "admin";
            const dirty = state.pendingRole !== state.savedRole;
            const saving = state.status.kind === "saving";
            return (
              <tr key={u.id}>
                <td className="px-2 py-1.5 font-medium">
                  {u.full_name ?? "-"}
                  {isSelf && (
                    <span className="ml-2 text-muted-foreground text-xs">
                      (you)
                    </span>
                  )}
                </td>
                <td className="px-2 py-1.5">{u.email}</td>
                <td className="px-2 py-1.5">
                  <label className="sr-only" htmlFor={`role-${u.id}`}>
                    Role for {u.email}
                  </label>
                  <select
                    className="rounded border border-border/60 bg-background px-2 py-1 text-sm"
                    disabled={saving || pending}
                    id={`role-${u.id}`}
                    onChange={(e) =>
                      setRow(u.id, {
                        pendingRole: e.target.value as AdminRole,
                        status: { kind: "idle" },
                      })
                    }
                    value={state.pendingRole}
                  >
                    {ROLE_OPTIONS.map((r) => (
                      <option key={r} value={r}>
                        {r}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1.5 text-right">
                  <div className="flex items-center justify-end gap-2">
                    {state.status.kind === "saved" && !dirty && (
                      <output className="text-primary text-xs">Saved</output>
                    )}
                    {state.status.kind === "error" && (
                      <span className="text-destructive text-xs" role="alert">
                        {state.status.message}
                      </span>
                    )}
                    <button
                      className="rounded border border-primary/40 bg-primary/10 px-3 py-1 text-primary text-xs hover:bg-primary/20 disabled:cursor-not-allowed disabled:opacity-40"
                      disabled={!dirty || saving || pending || selfDemotion}
                      onClick={() => save(u)}
                      title={
                        selfDemotion
                          ? "You cannot demote your own admin role."
                          : undefined
                      }
                      type="button"
                    >
                      {saving ? "Saving..." : "Save"}
                    </button>
                  </div>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
