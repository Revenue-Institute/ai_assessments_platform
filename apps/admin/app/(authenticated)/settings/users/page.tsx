import { ApiError, fetchAdminMe, listAdminUsers } from "@/lib/api";
import { AlertBanner } from "@/components/alert-banner";

import { Header } from "../../components/header";
import { UsersTable } from "./users-table";

export const dynamic = "force-dynamic";

export default async function SettingsUsersPage() {
  const [meResult, usersResult] = await Promise.allSettled([
    fetchAdminMe(),
    listAdminUsers(),
  ]);
  const me = meResult.status === "fulfilled" ? meResult.value : null;
  const meError =
    meResult.status === "rejected"
      ? meResult.reason instanceof ApiError
        ? meResult.reason.message
        : "Could not load profile."
      : null;
  const users = usersResult.status === "fulfilled" ? usersResult.value : [];
  const usersError =
    usersResult.status === "rejected"
      ? usersResult.reason instanceof ApiError
        ? usersResult.reason.message
        : "Could not load internal users."
      : null;

  return (
    <>
      <Header page="Users" pages={["Settings"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <p className="eyebrow-label">Your account</p>
          <AccountPanel error={meError} me={me} />
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-6">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="font-medium text-sm">Internal users</h2>
            <p className="text-muted-foreground text-xs">
              {users.length} {users.length === 1 ? "account" : "accounts"}
            </p>
          </div>
          {usersError ? (
            <AlertBanner>{usersError}</AlertBanner>
          ) : (
            <UsersTable currentUserId={me?.user_id ?? null} users={users} />
          )}
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-6">
          <h2 className="font-medium text-sm">Inviting new users</h2>
          <p className="mt-2 text-muted-foreground text-sm">
            Use the Supabase Dashboard for invites. v1 ships role management
            here; self-serve invitation flow lands in v1.1.
          </p>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground text-sm">
            <li>
              Open the Supabase project, then Authentication, then Users, and
              invite the email.
            </li>
            <li>
              Once they confirm, insert a row into <code>public.users</code>{" "}
              with their <code>auth.users.id</code> and the desired role.
            </li>
            <li>
              They can sign in at <code>/sign-in</code> and you can adjust their
              role above.
            </li>
          </ol>
        </section>
      </div>
    </>
  );
}

function AccountPanel({
  error,
  me,
}: {
  error: string | null;
  me: Awaited<ReturnType<typeof fetchAdminMe>> | null;
}) {
  if (error) {
    return <AlertBanner className="mt-2">{error}</AlertBanner>;
  }
  if (!me) {
    return <p className="mt-2 text-muted-foreground text-sm">Loading...</p>;
  }
  return (
    <dl className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
      <div>
        <dt className="text-muted-foreground text-xs">Name</dt>
        <dd className="mt-0.5 font-medium">{me.full_name ?? "-"}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground text-xs">Email</dt>
        <dd className="mt-0.5 font-medium">{me.email}</dd>
      </div>
      <div>
        <dt className="text-muted-foreground text-xs">Role</dt>
        <dd className="mt-0.5 font-medium capitalize">{me.role}</dd>
      </div>
    </dl>
  );
}
