import type { Metadata } from "next";
import { PromptMarkdown } from "@repo/design-system/components/prompt-markdown";
import Link from "next/link";
import { notFound, redirect } from "next/navigation";

import {
  ApiError,
  type AttemptEvent,
  type CompetencyDistributionResponse,
  cancelAssignment,
  competencyDistribution,
  getAssignment,
  listAssignmentEvents,
  rescoreAssignment,
  rescoreAttempt,
  resendAssignmentEmail,
  subjectCompetencyScores,
} from "@/lib/api";
import { SubmitButton } from "@/components/submit-button";

import { DistributionBox } from "../../components/distribution-box";
import { Header } from "../../components/header";
import { IntegrityScore } from "../../components/integrity-score";
import { IntegrityEventTimeline } from "./integrity-timeline";
import { ScoringListener } from "./scoring-listener";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id } = await params;
  try {
    const detail = await getAssignment(id);
    return { title: detail.subject_full_name ?? "Assignment" };
  } catch {
    return { title: "Assignment" };
  }
}

export default async function AssignmentDetailPage({
  params,
}: {
  params: Params;
}) {
  const { id } = await params;

  const [detailResult, eventsResult] = await Promise.allSettled([
    getAssignment(id),
    listAssignmentEvents(id),
  ]);

  if (detailResult.status === "rejected") {
    if (detailResult.reason instanceof ApiError && detailResult.reason.status === 404) {
      notFound();
    }
    throw detailResult.reason;
  }

  const detail = detailResult.value;
  // Soft fail: timeline is auxiliary; the rest of the page still loads.
  const events: AttemptEvent[] =
    eventsResult.status === "fulfilled" ? eventsResult.value : [];

  // §11.3: pull subject competency scores, match to this assignment, fetch team distribution per competency. Soft-fails.
  const distributionRows: Array<{
    candidate_score_pct: number;
    competency_id: string;
    stats: CompetencyDistributionResponse;
  }> = [];
  try {
    const subjectScores = await subjectCompetencyScores(detail.subject_id);
    const candidateForAssignment = subjectScores.trends
      .map((trend) => {
        const point = trend.points.find((p) => p.assignment_id === id);
        if (!point) {
          return null;
        }
        return {
          competency_id: trend.competency_id,
          score_pct: point.score_pct,
        };
      })
      .filter(
        (row): row is { competency_id: string; score_pct: number } =>
          row != null
      );

    const distributions = await Promise.all(
      candidateForAssignment.map((row) =>
        competencyDistribution({
          competency_id: row.competency_id,
          subject_id: detail.subject_id,
          assignment_id: id,
          exclude_subject_id: detail.subject_id,
        })
          .then((stats) => ({
            candidate_score_pct: row.score_pct,
            competency_id: row.competency_id,
            stats,
          }))
          .catch(() => null)
      )
    );
    distributionRows.push(...distributions.filter((d) => d != null));
  } catch {
    // Distributions are best-effort; assignment detail must still load.
  }

  async function cancel(): Promise<void> {
    "use server";
    try {
      await cancelAssignment(id);
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    redirect(`/assignments/${id}`);
  }

  async function rescoreAll(): Promise<void> {
    "use server";
    try {
      await rescoreAssignment(id);
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    redirect(`/assignments/${id}`);
  }

  async function resendEmail(): Promise<void> {
    "use server";
    try {
      await resendAssignmentEmail(id);
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    redirect(`/assignments/${id}`);
  }

  async function rescoreOne(formData: FormData): Promise<void> {
    "use server";
    const attemptId = String(formData.get("attempt_id") ?? "");
    if (!attemptId) return;
    try {
      await rescoreAttempt(attemptId);
    } catch (e) {
      if (!(e instanceof ApiError)) throw e;
    }
    redirect(`/assignments/${id}`);
  }

  return (
    <>
      <Header
        page={detail.subject_full_name ?? "Assignment"}
        pages={["Assignments"]}
      />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <RelatedEntities detail={detail} />

        <section className="grid grid-cols-1 gap-4 rounded-xl border border-border/50 bg-muted/30 p-4 sm:grid-cols-2 md:grid-cols-4">
          <Stat label="Status" value={detail.status} />
          <Stat
            label="Assessment"
            value={detail.assessment_title ?? detail.module_title ?? "-"}
          />
          <Stat
            label="Score"
            value={
              <span className="inline-flex items-center gap-2">
                {detail.final_score != null && detail.max_possible_score != null
                  ? `${detail.final_score} / ${detail.max_possible_score}`
                  : "-"}
                <ScoringListener assignmentId={id} />
              </span>
            }
          />
          <Stat
            label="Integrity"
            value={<IntegrityScore fallback score={detail.integrity_score} />}
          />
          <Stat
            label="Started"
            value={
              detail.started_at
                ? new Date(detail.started_at).toLocaleString()
                : "-"
            }
          />
          <Stat
            label="Completed"
            value={
              detail.completed_at
                ? new Date(detail.completed_at).toLocaleString()
                : "-"
            }
          />
          <Stat
            label="Expires"
            value={new Date(detail.expires_at).toLocaleString()}
          />
          <Stat
            label="Active time"
            value={
              detail.total_time_seconds != null
                ? `${Math.round(detail.total_time_seconds / 60)} min`
                : "-"
            }
          />
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-3 font-medium text-sm">Attempts</h2>
          {detail.attempts.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No attempts yet. Attempts are created lazily when the candidate
              views each question.
            </p>
          ) : (
            <ol className="space-y-3 text-sm">
              {detail.attempts.map((a, i) => (
                <li
                  className="scroll-mt-20 rounded border border-border/40 bg-background/30 p-3 target:ring-2 target:ring-primary/60"
                  id={`attempt-${a.id}`}
                  key={a.id}
                >
                  <div className="flex items-center justify-between gap-2">
                    <p className="font-medium">
                      Question {i + 1}
                      {a.needs_review && (
                        <span className="ml-2 rounded bg-warning/20 px-2 py-0.5 font-medium text-[10px] text-warning uppercase tracking-wide">
                          Needs review
                        </span>
                      )}
                    </p>
                    <p className="text-muted-foreground text-xs">
                      {a.submitted_at ? "submitted" : "in progress"}
                    </p>
                  </div>
                  <div className="prompt-markdown-condensed mt-1 line-clamp-3 text-muted-foreground text-xs">
                    <PromptMarkdown source={a.rendered_prompt} />
                  </div>
                  {a.raw_answer && (
                    <details className="mt-2">
                      <summary className="cursor-pointer text-muted-foreground text-xs hover:text-primary">
                        View raw answer
                      </summary>
                      <pre className="mt-2 max-h-64 overflow-auto rounded bg-muted/40 p-2 text-xs">
                        {JSON.stringify(a.raw_answer, null, 2)}
                      </pre>
                    </details>
                  )}
                  {a.score_rationale && (
                    <p className="mt-2 rounded border border-border/40 bg-muted/30 p-2 text-muted-foreground text-xs">
                      {a.score_rationale}
                    </p>
                  )}
                  <div className="mt-2 flex flex-wrap items-center gap-3 text-muted-foreground text-xs">
                    <span>
                      Score:{" "}
                      {a.score != null
                        ? `${a.score} / ${a.max_score}`
                        : `- / ${a.max_score}`}
                    </span>
                    {a.scorer_model && (
                      <span>
                        Scorer: <code>{a.scorer_model}</code>
                      </span>
                    )}
                    {a.scorer_confidence != null && (
                      <span>Confidence: {a.scorer_confidence}</span>
                    )}
                    {a.active_time_seconds != null && (
                      <span>Active: {a.active_time_seconds}s</span>
                    )}
                    {a.submitted_at && (
                      <form action={rescoreOne} className="ml-auto">
                        <input name="attempt_id" type="hidden" value={a.id} />
                        <SubmitButton
                          className="rounded border border-primary/40 bg-primary/10 px-2 py-1 text-primary text-xs hover:bg-primary/20"
                          pendingLabel="Rescoring..."
                        >
                          Rescore
                        </SubmitButton>
                      </form>
                    )}
                  </div>
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-3 font-medium text-sm">
            Competency distribution vs team
          </h2>
          {distributionRows.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No team distribution available yet. Scores land here once this
              assignment has scored competencies and a team baseline exists.
            </p>
          ) : (
            <ul className="grid gap-3 md:grid-cols-2">
              {distributionRows.map((row) => (
                <li
                  className="rounded border border-border/40 bg-background/30 p-3"
                  key={row.competency_id}
                >
                  <p className="font-medium text-sm">{row.competency_id}</p>
                  <p className="mt-0.5 text-muted-foreground text-xs">
                    Candidate {Math.round(row.candidate_score_pct)}% vs team
                  </p>
                  <div className="mt-2">
                    <DistributionBox
                      candidateScore={row.candidate_score_pct}
                      stats={row.stats}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-3 font-medium text-sm">Integrity timeline</h2>
          <IntegrityEventTimeline events={events} />
        </section>

        <AssignmentActions
          cancel={cancel}
          rescoreAll={rescoreAll}
          resendEmail={resendEmail}
          status={detail.status}
        />
      </div>
    </>
  );
}

function RelatedEntities({
  detail,
}: {
  detail: Awaited<ReturnType<typeof getAssignment>>;
}) {
  return (
    <nav
      aria-label="Related entities"
      className="flex flex-wrap gap-3 text-muted-foreground text-xs"
    >
      {detail.subject_id && (
        <Link
          className="hover:text-primary hover:underline"
          href={`/candidates/${detail.subject_id}`}
        >
          ↗ Candidate:{" "}
          {detail.subject_full_name ?? detail.subject_id.slice(0, 8)}
        </Link>
      )}
      {detail.assessment_id && (
        <Link
          className="hover:text-primary hover:underline"
          href={`/assessments/${detail.assessment_id}`}
        >
          ↗ Assessment:{" "}
          {detail.assessment_title ?? detail.assessment_id.slice(0, 8)}
        </Link>
      )}
      {!detail.assessment_id && detail.module_id && (
        <Link
          className="hover:text-primary hover:underline"
          href={`/modules/${detail.module_id}`}
        >
          ↗ Module: {detail.module_title ?? detail.module_id.slice(0, 8)}
        </Link>
      )}
    </nav>
  );
}

function AssignmentActions({
  cancel,
  rescoreAll,
  resendEmail,
  status,
}: {
  cancel: () => Promise<void>;
  rescoreAll: () => Promise<void>;
  resendEmail: () => Promise<void>;
  status: string;
}) {
  const canManageLink =
    status !== "completed" && status !== "cancelled" && status !== "expired";

  return (
    <div className="flex flex-wrap gap-2">
      {status === "completed" && (
        <form action={rescoreAll}>
          <SubmitButton
            className="rounded border border-primary/50 bg-primary/10 px-3 py-2 text-primary text-sm hover:bg-primary/20"
            pendingLabel="Rescoring..."
          >
            Rescore all attempts
          </SubmitButton>
        </form>
      )}
      {canManageLink && (
        <>
          <form action={resendEmail}>
            <SubmitButton
              className="rounded border border-primary/50 bg-primary/10 px-3 py-2 text-primary text-sm hover:bg-primary/20"
              pendingLabel="Sending..."
            >
              Resend magic link
            </SubmitButton>
          </form>
          <form action={cancel}>
            <SubmitButton
              className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm hover:bg-destructive/25"
              pendingLabel="Cancelling..."
            >
              Cancel assignment
            </SubmitButton>
          </form>
        </>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div>
      <p className="text-muted-foreground text-xs uppercase tracking-wide">
        {label}
      </p>
      <p className="font-medium text-sm">{value}</p>
    </div>
  );
}
