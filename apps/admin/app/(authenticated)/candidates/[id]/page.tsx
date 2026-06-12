import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  type AssignmentSummary,
  type CompetencyDistributionResponse,
  type SubjectCompetencyTrend,
  ApiError,
  competencyDistribution,
  listAssignments,
  listSubjects,
  subjectCompetencyScores,
} from "@/lib/api";
import { AlertBanner } from "@/components/alert-banner";

import { CompetencyRadar } from "../../components/competency-radar";
import { DistributionBox } from "../../components/distribution-box";
import { Header } from "../../components/header";
import { IntegrityScore } from "../../components/integrity-score";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id } = await params;
  try {
    const subjects = await listSubjects();
    const subject = subjects.find((s) => s.id === id);
    return { title: subject?.full_name ?? "Candidate" };
  } catch {
    return { title: "Candidate" };
  }
}

export default async function CandidateDetailPage({
  params,
}: {
  params: Params;
}) {
  const { id } = await params;

  let trends: SubjectCompetencyTrend[] = [];
  let allAssignments: AssignmentSummary[] = [];
  let error: string | null = null;
  let distributions: Record<string, CompetencyDistributionResponse> = {};

  try {
    const [scores, assignments] = await Promise.all([
      subjectCompetencyScores(id),
      listAssignments(),
    ]);
    trends = scores.trends;
    allAssignments = assignments.filter((a) => a.subject_id === id);

    if (trends.length > 0) {
      const distArray = await Promise.all(
        trends.map((t) =>
          competencyDistribution({
            competency_id: t.competency_id,
            exclude_subject_id: id,
          }).catch(() => null)
        )
      );
      distributions = Object.fromEntries(
        distArray
          .filter((d): d is CompetencyDistributionResponse => d != null)
          .map((d) => [d.competency_id, d])
      );
    }
  } catch (e) {
    if (e instanceof ApiError) {
      if (e.status === 404) notFound();
      error = e.message;
    } else {
      throw e;
    }
  }

  const radarSlices = trends.map((t) => ({
    competency_id: t.competency_id,
    score_pct: t.latest_score_pct,
  }));

  return (
    <>
      <Header
        page={candidateDisplayName(allAssignments)}
        pages={["Candidates"]}
      />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <AlertBanner>{error}</AlertBanner>

        <section className="grid gap-4 lg:grid-cols-2">
          <CompetencyRadar slices={radarSlices} />
          <CompetencyTrendList distributions={distributions} trends={trends} />
        </section>

        <AssignmentHistory assignments={allAssignments} />
      </div>
    </>
  );
}

function candidateDisplayName(assignments: AssignmentSummary[]): string {
  for (const a of assignments) {
    if (a.subject_full_name) {
      return a.subject_full_name;
    }
  }
  return "Candidate";
}

function CompetencyTrendList({
  trends,
  distributions,
}: {
  trends: SubjectCompetencyTrend[];
  distributions: Record<string, CompetencyDistributionResponse>;
}) {
  if (trends.length === 0) {
    return (
      <section className="rounded-xl border border-border/50 bg-muted/20 p-6 text-center text-muted-foreground text-sm">
        No competency trends yet.
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
      <h2 className="mb-3 font-medium text-sm">Competency trends</h2>
      <ul className="space-y-3 text-sm">
        {trends.map((t) => {
          const dist = distributions[t.competency_id];
          return (
            <li
              className="rounded border border-border/40 bg-background/30 p-3"
              key={t.competency_id}
            >
              <div className="flex items-baseline justify-between gap-3">
                <p className="font-medium">{t.competency_id}</p>
                <p className="text-primary text-xs">
                  {Math.round(t.latest_score_pct)}%
                  {t.delta_vs_previous != null && t.delta_vs_previous !== 0 && (
                    <span
                      className={`ml-1 ${t.delta_vs_previous >= 0 ? "text-primary" : "text-destructive"}`}
                    >
                      ({t.delta_vs_previous >= 0 ? "+" : ""}
                      {t.delta_vs_previous.toFixed(1)} vs prior)
                    </span>
                  )}
                </p>
              </div>
              <Sparkline points={t.points.map((p) => p.score_pct)} />
              <p className="mt-1 text-muted-foreground text-xs">
                {t.points.length} attempt{t.points.length === 1 ? "" : "s"}
              </p>
              {dist && dist.sample_size > 0 && (
                <div className="mt-2 border-border/30 border-t pt-2">
                  <p className="mb-1 text-[11px] text-muted-foreground uppercase tracking-wide">
                    vs. team
                  </p>
                  <DistributionBox
                    candidateScore={t.latest_score_pct}
                    stats={dist}
                  />
                </div>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}

function Sparkline({ points }: { points: number[] }) {
  if (points.length === 0) {
    return null;
  }
  const W = 240;
  const H = 36;
  const max = 100;
  const stepX = points.length > 1 ? W / (points.length - 1) : 0;
  const coords = points.map((p, i) => ({
    x: i * stepX,
    y: H - (Math.max(0, Math.min(max, p)) / max) * H,
    p,
  }));
  const path = coords
    .map(({ x, y }, i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`)
    .join(" ");
  return (
    <svg
      aria-hidden="true"
      className="mt-1 text-primary"
      height={H}
      viewBox={`0 0 ${W} ${H}`}
      width={W}
    >
      <path
        d={path}
        fill="none"
        stroke="currentColor"
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth={2}
      />
      {coords.map(({ x, y, p }) => (
        <circle
          cx={x}
          cy={y}
          fill="currentColor"
          key={`${x.toFixed(1)}-${y.toFixed(1)}-${p}`}
          r={2}
        />
      ))}
    </svg>
  );
}

function AssignmentHistory({
  assignments,
}: {
  assignments: AssignmentSummary[];
}) {
  if (assignments.length === 0) {
    return (
      <section className="rounded-xl border border-border/50 bg-muted/20 p-6 text-center text-muted-foreground text-sm">
        No assignments yet.
      </section>
    );
  }
  return (
    <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
      <h2 className="mb-3 font-medium text-sm">Assignment history</h2>
      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground text-xs uppercase">
          <tr>
            <th className="px-2 py-1" scope="col">
              Module
            </th>
            <th className="px-2 py-1" scope="col">
              Status
            </th>
            <th className="px-2 py-1" scope="col">
              Score
            </th>
            <th className="px-2 py-1" scope="col">
              Integrity
            </th>
            <th className="px-2 py-1" scope="col">
              Created
            </th>
            <th className="px-2 py-1" scope="col">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-border/30">
          {assignments.map((a) => (
            <tr key={a.id}>
              <td className="px-2 py-1.5">
                {a.assessment_title ?? a.module_title ?? "-"}
              </td>
              <td className="px-2 py-1.5">{a.status}</td>
              <td className="px-2 py-1.5">
                {a.final_score != null && a.max_possible_score != null
                  ? `${a.final_score} / ${a.max_possible_score}`
                  : "-"}
              </td>
              <td className="px-2 py-1.5">
                <IntegrityScore fallback score={a.integrity_score} />
              </td>
              <td className="px-2 py-1.5 text-muted-foreground text-xs">
                {new Date(a.created_at).toLocaleString()}
              </td>
              <td className="px-2 py-1.5 text-right">
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
    </section>
  );
}
