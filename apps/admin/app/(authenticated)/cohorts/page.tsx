import {
  ApiError,
  type CohortHeatmapResponse,
  cohortHeatmap,
  type SubjectType,
  weakSpots,
  type WeakSpotsResponse,
} from "@/lib/api";
import { CompetencyHeatmap } from "../components/competency-heatmap";
import { Header } from "../components/header";

export const dynamic = "force-dynamic";

type SearchParams = Promise<{
  type?: SubjectType;
  domain?: string;
  days?: string;
  threshold?: string;
}>;

const SUBJECT_TYPES: Array<SubjectType | ""> = ["", "candidate", "employee"];
const DAYS_OPTIONS = ["30", "90", "180", "365", "730"];

export default async function CohortsPage({
  searchParams,
}: {
  searchParams: SearchParams;
}) {
  const params = await searchParams;
  const subjectType = (params.type || undefined) as SubjectType | undefined;
  const domain = params.domain?.trim() || undefined;
  const days = params.days ? Number.parseInt(params.days, 10) : 365;
  const threshold = params.threshold
    ? Math.max(0, Math.min(100, Number.parseFloat(params.threshold)))
    : 60;

  let heatmap: CohortHeatmapResponse = {
    subjects: [],
    competencies: [],
    cells: [],
    team_average_pct: {},
  };
  let weak: WeakSpotsResponse = { threshold_pct: threshold, weak_spots: [] };
  let error: string | null = null;
  try {
    [heatmap, weak] = await Promise.all([
      cohortHeatmap({ type: subjectType, domain, days }),
      weakSpots({ type: subjectType, threshold_pct: threshold }),
    ]);
  } catch (e) {
    if (e instanceof ApiError) error = e.message;
    else throw e;
  }

  return (
    <>
      <Header page="Cohorts" pages={[]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <h1 className="font-semibold text-xl">Cohort benchmarks</h1>
          <p className="text-muted-foreground text-sm">
            Latest score per (subject, competency). Filter by subject type or
            domain. Weak-spot detection runs across the same filter.
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
              Window (days)
            </span>
            <select
              className="rounded border border-border/60 bg-background px-3 py-1.5 text-sm"
              defaultValue={String(days)}
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
          <button
            className="rounded bg-emerald-500 px-3 py-2 text-emerald-950 text-sm hover:bg-emerald-400"
            type="submit"
          >
            Apply
          </button>
        </form>

        {error && (
          <p className="rounded border border-red-900/50 bg-red-950/30 px-3 py-2 text-red-200 text-sm">
            {error}
          </p>
        )}

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
                  className="flex items-center justify-between rounded border border-amber-900/40 bg-amber-950/20 px-3 py-2 text-sm"
                  key={w.competency_id}
                >
                  <span className="truncate">{w.competency_id}</span>
                  <span className="text-amber-200">
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
