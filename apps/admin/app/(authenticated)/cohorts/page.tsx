import type { Metadata } from "next";
import { AlertBanner } from "@/components/alert-banner";
import {
  type CohortHeatmapResponse,
  cohortHeatmap,
  type SubjectType,
  type WeakSpotsResponse,
  weakSpots,
} from "@/lib/api";
import { loadOrApiError } from "@/lib/api-helpers";

import { CompetencyHeatmap } from "../components/competency-heatmap";
import { Header } from "../components/header";

export const metadata: Metadata = { title: "Cohorts" };

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  type?: SubjectType;
  domain?: string;
  days?: string;
  threshold?: string;
  role?: string;
  start_date?: string;
  end_date?: string;
}>;

const SUBJECT_TYPES: Array<SubjectType | ""> = ["", "candidate", "employee"];
const DAYS_OPTIONS = ["30", "90", "180", "365", "730"];
const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

function parseIsoDate(value: string | undefined): string | undefined {
  if (value && ISO_DATE_RE.test(value)) {
    return value;
  }
  return undefined;
}

function resolveDays(
  usingExplicitWindow: boolean,
  rawDays: string | undefined
): number | undefined {
  if (usingExplicitWindow) {
    return;
  }
  if (rawDays) {
    return Number.parseInt(rawDays, 10);
  }
  return 365;
}

export default async function CohortsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const subjectType = (params.type || undefined) as SubjectType | undefined;
  const domain = params.domain?.trim() || undefined;
  const role = params.role?.trim() || undefined;
  const startDate = parseIsoDate(params.start_date);
  const endDate = parseIsoDate(params.end_date);
  // When an explicit date window is set, skip the rolling-days input to avoid double-clipping the range.
  const usingExplicitWindow = Boolean(startDate || endDate);
  const days = resolveDays(usingExplicitWindow, params.days);
  const threshold = params.threshold
    ? Math.max(0, Math.min(100, Number.parseFloat(params.threshold)))
    : 60;

  const emptyHeatmap: CohortHeatmapResponse = {
    subjects: [],
    competencies: [],
    cells: [],
    team_average_pct: {},
  };
  const emptyWeak: WeakSpotsResponse = {
    threshold_pct: threshold,
    weak_spots: [],
  };
  const { data, error } = await loadOrApiError(() =>
    Promise.all([
      cohortHeatmap({
        type: subjectType,
        domain,
        days,
        role,
        start_date: startDate,
        end_date: endDate,
      }),
      weakSpots({ type: subjectType, threshold_pct: threshold }),
    ])
  );
  const [heatmap, weak] = data ?? [emptyHeatmap, emptyWeak];

  return (
    <>
      <Header page="Cohorts" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h2 className="font-semibold text-xl">Cohort benchmarks</h2>
          <p className="text-muted-foreground text-sm">
            Latest score per (subject, competency). Filter by subject type,
            domain, role applied for, or an explicit date range. Weak-spot
            detection runs across the same filter.
          </p>
        </section>

        <form
          action="/cohorts"
          className="flex flex-wrap items-end gap-3 rounded-xl border border-border/50 bg-muted/20 p-3"
          method="get"
        >
          <label className="space-y-1">
            <span className="block text-muted-foreground text-xs uppercase">
              Subject type
            </span>
            <select
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm"
              defaultValue={subjectType ?? ""}
              name="type"
            >
              {SUBJECT_TYPES.map((t) => (
                <option key={t || "any"} value={t}>
                  {t || "any"}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-muted-foreground text-xs uppercase">
              Domain
            </span>
            <input
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm"
              defaultValue={domain ?? ""}
              name="domain"
              placeholder="hubspot, ai..."
            />
          </label>
          <label className="space-y-1">
            <span className="block text-muted-foreground text-xs uppercase">
              Role
            </span>
            <input
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm"
              defaultValue={role ?? ""}
              name="role"
              placeholder="e.g. SDR, RevOps Manager"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-muted-foreground text-xs uppercase">
              Window (days)
            </span>
            <select
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm disabled:opacity-50"
              defaultValue={String(days ?? 365)}
              disabled={usingExplicitWindow}
              name="days"
            >
              {DAYS_OPTIONS.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </select>
          </label>
          <label className="space-y-1">
            <span className="block text-muted-foreground text-xs uppercase">
              Start date
            </span>
            <input
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm"
              defaultValue={startDate ?? ""}
              max={endDate ?? undefined}
              name="start_date"
              type="date"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-muted-foreground text-xs uppercase">
              End date
            </span>
            <input
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm"
              defaultValue={endDate ?? ""}
              min={startDate ?? undefined}
              name="end_date"
              type="date"
            />
          </label>
          <label className="space-y-1">
            <span className="block text-muted-foreground text-xs uppercase">
              Weak-spot threshold (%)
            </span>
            <input
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm"
              defaultValue={String(threshold)}
              max="100"
              min="0"
              name="threshold"
              type="number"
            />
          </label>
          <button className="btn-primary text-sm" type="submit">
            Apply
          </button>
        </form>

        <AlertBanner>{error}</AlertBanner>

        <CompetencyHeatmap data={heatmap} />

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-2 font-medium text-sm">
            Weak spots (median below {weak.threshold_pct.toFixed(0)}%)
          </h2>
          {weak.weak_spots.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No competencies are below the threshold.
            </p>
          ) : (
            <ul className="grid gap-2 md:grid-cols-2 lg:grid-cols-3">
              {weak.weak_spots.map((w) => (
                <li
                  className="flex items-center justify-between rounded border border-warning/40 bg-warning/10 px-3 py-2 text-sm"
                  key={w.competency_id}
                >
                  <span className="truncate">{w.competency_id}</span>
                  <span className="text-warning">
                    {Math.round(w.median_pct)}% · n={w.sample_size}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </section>
      </div>
    </>
  );
}
