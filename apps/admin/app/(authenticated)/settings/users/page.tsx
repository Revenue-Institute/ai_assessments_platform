import { ApiError, fetchAdminMe } from "@/lib/api";
import { Header } from "../../components/header";

export const dynamic = "force-dynamic";

export default async function SettingsUsersPage() {
  let me: Awaited<ReturnType<typeof fetchAdminMe>> | null = null;
  let error: string | null = null;
  try {
    me = await fetchAdminMe();
  } catch (e) {
    error = e instanceof ApiError ? e.message : "Could not load profile.";
  }

  return (
    <>
      <Header page="Users" pages={["Settings"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-6">
          <p className="eyebrow-label">Your account</p>
          {error ? (
            <p
              className="mt-2 rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
              role="alert"
            >
              {error}
            </p>
          ) : me ? (
            <dl className="mt-3 grid grid-cols-2 gap-3 text-sm md:grid-cols-3">
              <div>
                <dt className="text-muted-foreground text-xs">Name</dt>
                <dd className="mt-0.5 font-medium">{me.full_name ?? "—"}</dd>
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
          ) : (
            <p className="mt-2 text-muted-foreground text-sm">Loading…</p>
          )}
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-6">
          <h2 className="font-medium text-sm">Provisioning new users (v1)</h2>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted-foreground text-sm">
            <li>
              Go to your Supabase project &rarr; <em>Authentication &rarr; Users</em>
              and invite the email.
            </li>
            <li>
              Once they confirm, insert a row into <code>public.users</code> with
              their <code>auth.users.id</code> and the desired role
              (<code>admin</code> / <code>reviewer</code> / <code>viewer</code>).
            </li>
            <li>
              They will be able to sign in immediately at <code>/sign-in</code>.
            </li>
          </ol>
          <p className="mt-3 text-muted-foreground text-xs">
            A self-serve invite + role-management UI is on the v1.1 roadmap.
            Until then this page is read-only by design.
          </p>
        </section>
      </div>
    </>
  );
}
