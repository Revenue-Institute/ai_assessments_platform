import type { Metadata } from "next";
import Link from "next/link";

import {
  type AssignmentSummary,
  listAssignments,
  listModules,
  listSeries,
  type ModuleSummary,
} from "@/lib/api";
import { AlertBanner } from "@/components/alert-banner";
import { loadOrApiError } from "@/lib/api-helpers";

import { Header } from "./components/header";
import { IntegrityScore } from "./components/integrity-score";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Dashboard",
  description:
    "Overview of active assignments, pending reviews, integrity flags, and module readiness.",
};

export default async function DashboardPage() {
  const { data, error } = await loadOrApiError(() =>
    Promise.all([listAssignments(), listModules(), listSeries()])
  );
  const [assignments, modules, seriesRows] = data ?? [
    [] as AssignmentSummary[],
    [] as ModuleSummary[],
    [],
  ];
  const seriesCount = seriesRows.length;

  const now = Date.now();
  const active = assignments.filter((a) => a.status === "in_progress");
  const pending = assignments.filter((a) => a.status === "pending");
  const completed = assignments.filter((a) => a.status === "completed");
  const review = assignments.filter((a) => a.needs_review);
  const integrityFlags = completed.filter(
    (a) => a.integrity_score != null && a.integrity_score < 85
  );
  const expiring = pending.filter((a) => {
    const expires = new Date(a.expires_at).getTime();
    return expires > now && expires - now <= 72 * 60 * 60 * 1000;
  });
  const publishedModules = modules.filter((m) => m.status === "published");
  const draftModules = modules.filter((m) => m.status === "draft");
  const recentAssignments = [...assignments]
    .sort(
      (a, b) =>
        new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )
    .slice(0, 6);

  return (
    <>
      <Header page="Dashboard" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <AlertBanner>{error}</AlertBanner>

        <section className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          <MetricCard
            href="/assignments"
            label="Active now"
            tone={active.length > 0 ? "primary" : "neutral"}
            value={active.length}
          />
          <MetricCard
            href="/assignments?review=1"
            label="Needs review"
            tone={review.length > 0 ? "warning" : "neutral"}
            value={review.length}
          />
          <MetricCard
            href="/assignments"
            label="Integrity flags"
            tone={integrityFlags.length > 0 ? "destructive" : "neutral"}
            value={integrityFlags.length}
          />
          <MetricCard
            href="/modules"
            label="Published modules"
            tone={publishedModules.length > 0 ? "primary" : "neutral"}
            value={publishedModules.length}
          />
        </section>

        <section className="grid gap-4 xl:grid-cols-[1.35fr_0.65fr]">
          <div className="rounded-xl border border-border/50 bg-muted/20 p-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div>
                <h2 className="font-semibold text-lg">Recent assignments</h2>
                <p className="text-muted-foreground text-sm">
                  Latest candidate and employee assessment activity.
                </p>
              </div>
              <Link
                className="text-primary text-sm hover:underline"
                href="/assignments"
              >
                View all
              </Link>
            </div>
            {recentAssignments.length === 0 ? (
              <EmptyAction
                action="Issue magic links"
                href="/assignments/new"
                message="No assignments have been created yet."
              />
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead className="text-left text-muted-foreground text-xs uppercase">
                    <tr>
                      <th className="px-2 py-2" scope="col">
                        Subject
                      </th>
                      <th className="px-2 py-2" scope="col">
                        Assessment
                      </th>
                      <th className="px-2 py-2" scope="col">
                        Status
                      </th>
                      <th className="px-2 py-2" scope="col">
                        Score
                      </th>
                      <th className="px-2 py-2" scope="col">
                        Integrity
                      </th>
                      <th className="px-2 py-2" scope="col">
                        <span className="sr-only">Actions</span>
                      </th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {recentAssignments.map((a) => (
                      <tr key={a.id}>
                        <td className="px-2 py-2">
                          <p className="font-medium">
                            {a.subject_full_name ?? "Unknown subject"}
                          </p>
                          <p className="text-muted-foreground text-xs">
                            {a.subject_email ?? ""}
                          </p>
                        </td>
                        <td className="px-2 py-2">
                          {a.assessment_title ?? a.module_title ?? "-"}
                        </td>
                        <td className="px-2 py-2">
                          <StatusPill status={a.status} />
                        </td>
                        <td className="px-2 py-2">
                          {a.final_score != null && a.max_possible_score != null
                            ? `${a.final_score} / ${a.max_possible_score}`
                            : "-"}
                        </td>
                        <td className="px-2 py-2">
                          <IntegrityScore fallback score={a.integrity_score} />
                        </td>
                        <td className="px-2 py-2 text-right">
                          <Link
                            className="text-primary text-xs hover:underline"
                            href={`/assignments/${a.id}`}
                          >
                            Open
                          </Link>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>

          <div className="grid gap-4">
            <ActionPanel
              items={[
                {
                  count: expiring.length,
                  href: "/assignments",
                  label: "Pending links expiring in 72 hours",
                },
                {
                  count: draftModules.length,
                  href: "/modules",
                  label: "Draft modules to review",
                },
                {
                  count: seriesCount,
                  href: "/series",
                  label: "Active assessment series",
                },
              ]}
            />
            <QuickActions />
          </div>
        </section>
      </div>
    </>
  );
}

function MetricCard({
  href,
  label,
  value,
  tone,
}: {
  href: string;
  label: string;
  value: number;
  tone: "primary" | "warning" | "destructive" | "neutral";
}) {
  const toneClass = {
    primary: "text-primary",
    warning: "text-warning",
    destructive: "text-destructive",
    neutral: "text-foreground",
  }[tone];
  return (
    <Link
      className="rounded-xl border border-border/50 bg-muted/20 p-4 transition hover:border-primary/40 hover:bg-muted/30"
      href={href}
    >
      <p className="text-muted-foreground text-xs uppercase tracking-wide">
        {label}
      </p>
      <p className={`mt-2 font-semibold text-3xl ${toneClass}`}>{value}</p>
    </Link>
  );
}

function ActionPanel({
  items,
}: {
  items: Array<{ count: number; href: string; label: string }>;
}) {
  return (
    <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
      <h2 className="mb-3 font-medium text-sm">Operational queue</h2>
      <ul className="space-y-2">
        {items.map((item) => (
          <li key={item.label}>
            <Link
              className="flex items-center justify-between rounded border border-border/40 bg-background/40 px-3 py-2 text-sm hover:border-primary/40"
              href={item.href}
            >
              <span>{item.label}</span>
              <span className="font-medium text-primary">{item.count}</span>
            </Link>
          </li>
        ))}
      </ul>
    </section>
  );
}

function QuickActions() {
  return (
    <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
      <h2 className="mb-3 font-medium text-sm">Quick actions</h2>
      <div className="grid gap-2">
        <Link className="btn-primary text-sm" href="/modules/new">
          Generate module
        </Link>
        <Link className="btn-outline text-sm" href="/assignments/new">
          Issue assignment
        </Link>
        <Link className="btn-outline text-sm" href="/references">
          Add reference material
        </Link>
      </div>
    </section>
  );
}

function EmptyAction({
  action,
  href,
  message,
}: {
  action: string;
  href: string;
  message: string;
}) {
  return (
    <div className="rounded border border-border/60 border-dashed px-4 py-8 text-center">
      <p className="text-muted-foreground text-sm">{message}</p>
      <Link className="btn-primary mt-3 text-sm" href={href}>
        {action}
      </Link>
    </div>
  );
}

function StatusPill({ status }: { status: string }) {
  const tone =
    status === "completed"
      ? "bg-primary/20 text-primary"
      : status === "in_progress"
        ? "bg-warning/20 text-warning"
        : status === "cancelled" || status === "expired"
          ? "bg-muted text-muted-foreground"
          : "bg-secondary text-secondary-foreground";
  return (
    <span className={`rounded px-2 py-0.5 font-medium text-xs ${tone}`}>
      {status}
    </span>
  );
}
