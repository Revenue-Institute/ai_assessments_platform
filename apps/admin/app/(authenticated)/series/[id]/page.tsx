import Link from "next/link";
import { notFound } from "next/navigation";
import {
  ApiError,
  getSeriesDetail,
  getSeriesTrend,
  type SeriesDetail,
  type SeriesTrendLine,
  type SeriesTrendResponse,
} from "@/lib/api";
import { Header } from "../../components/header";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export default async function SeriesDetailPage({ params }: { params: Params }) {
  const { id } = await params;

  let detail: SeriesDetail;
  try {
    detail = await getSeriesDetail(id);
  } catch (e) {
    if (e instanceof ApiError && e.status === 404) {
      notFound();
    }
    throw e;
  }

  // Trend is auxiliary: a missing endpoint should not break the rest of the
  // page. Render the header, focus list, and assignments table even if the
  // backend trend route is offline (defensive against API rollout skew).
  let trend: SeriesTrendResponse | null = null;
  let trendError: string | null = null;
  try {
    trend = await getSeriesTrend(id);
  } catch (e) {
    trendError =
      e instanceof ApiError ? e.message : "Could not load trend data.";
  }

  const orderedAssignments = [...detail.assignments].sort(
    (a, b) => a.sequence_number - b.sequence_number
  );

  return (
    <>
      <Header page={detail.name} pages={["Series"]} />
      <div className="flex flex-1 flex-col gap-4 p-4 pt-0">
        <section className="rounded-xl border border-border/50 bg-muted/30 p-4">
          <div className="flex flex-wrap items-baseline justify-between gap-3">
            <div>
              <h1 className="font-semibold text-xl">{detail.name}</h1>
              <p className="text-muted-foreground text-sm">
                {detail.subject_full_name ? (
                  <Link
                    className="hover:text-primary hover:underline"
                    href={`/candidates/${detail.subject_id}`}
                  >
                    {detail.subject_full_name}
                  </Link>
                ) : (
                  "Subject"
                )}
                {detail.subject_email ? ` · ${detail.subject_email}` : ""}
              </p>
            </div>
            <dl className="grid grid-cols-3 gap-4 text-xs">
              <div>
                <dt className="text-muted-foreground uppercase tracking-wide">
                  Cadence
                </dt>
                <dd className="mt-0.5 font-medium text-sm">
                  {detail.cadence_days
                    ? `${detail.cadence_days} days`
                    : "ad-hoc"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground uppercase tracking-wide">
                  Next due
                </dt>
                <dd className="mt-0.5 font-medium text-sm">
                  {detail.next_due_at
                    ? new Date(detail.next_due_at).toLocaleString()
                    : "-"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground uppercase tracking-wide">
                  Assignments
                </dt>
                <dd className="mt-0.5 font-medium text-sm">
                  {detail.assignment_count}
                </dd>
              </div>
            </dl>
          </div>
          <div className="mt-3">
            <p className="text-muted-foreground text-xs uppercase tracking-wide">
              Competency focus
            </p>
            {detail.competency_focus.length === 0 ? (
              <p className="text-muted-foreground text-sm">-</p>
            ) : (
              <ul className="mt-1 flex flex-wrap gap-1.5">
                {detail.competency_focus.map((c) => (
                  <li
                    className="rounded border border-border/40 bg-background/40 px-2 py-0.5 text-xs"
                    key={c}
                  >
                    {c}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <div className="mb-3 flex items-baseline justify-between">
            <h2 className="font-medium text-sm">
              Competency trend across sequence
            </h2>
            <p className="text-muted-foreground text-xs">
              y = score % (0 to 100) · x = sequence number
            </p>
          </div>
          {trendError ? (
            <p
              className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
              role="alert"
            >
              {trendError}
            </p>
          ) : (
            <SeriesTrendChart focus={detail.competency_focus} trend={trend} />
          )}
        </section>

        <section className="rounded-xl border border-border/50 bg-muted/20 p-4">
          <h2 className="mb-3 font-medium text-sm">
            Assignments in this series
          </h2>
          {orderedAssignments.length === 0 ? (
            <p className="text-muted-foreground text-sm">
              No assignments have been linked or issued yet. Use "Issue next"
              from the series list to schedule the first attempt.
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead className="text-left text-muted-foreground text-xs uppercase">
                <tr>
                  <th className="px-2 py-1" scope="col">
                    Sequence
                  </th>
                  <th className="px-2 py-1" scope="col">
                    Status
                  </th>
                  <th className="px-2 py-1" scope="col">
                    Score
                  </th>
                  <th className="px-2 py-1" scope="col">
                    Completed
                  </th>
                  <th className="px-2 py-1" scope="col">
                    <span className="sr-only">Open</span>
                  </th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/30">
                {orderedAssignments.map((a) => (
                  <tr
                    className="cursor-pointer hover:bg-muted/40"
                    key={a.assignment_id}
                  >
                    <td className="px-2 py-1.5 font-medium">
                      #{a.sequence_number}
                    </td>
                    <td className="px-2 py-1.5">{a.status}</td>
                    <td className="px-2 py-1.5">
                      {a.final_score != null && a.max_possible_score != null
                        ? `${a.final_score} / ${a.max_possible_score}`
                        : "-"}
                    </td>
                    <td className="px-2 py-1.5 text-muted-foreground text-xs">
                      {a.completed_at
                        ? new Date(a.completed_at).toLocaleString()
                        : "-"}
                    </td>
                    <td className="px-2 py-1.5 text-right">
                      <Link
                        className="text-primary text-xs hover:underline"
                        href={`/assignments/${a.assignment_id}`}
                      >
                        Open
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      </div>
    </>
  );
}

interface ChartProps {
  focus: string[];
  trend: SeriesTrendResponse | null;
}

// Brand-leaning palette borrowed from the heatmap. Hand-picked so adjacent
// competency lines stay distinguishable in both themes; cycled when the
// focus list exceeds the array length.
const TREND_COLORS = [
  "rgb(10 143 93)", // brand forest
  "rgb(56 189 248)", // sky
  "rgb(217 119 6)", // amber
  "rgb(244 63 94)", // rose
  "rgb(167 139 250)", // violet
  "rgb(45 212 191)", // teal
];

function SeriesTrendChart({ focus, trend }: ChartProps) {
  const lines: SeriesTrendLine[] = trend?.trends ?? [];
  const usable = lines.filter((l) => l.points.length > 0);

  if (focus.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        This series has no competency focus to plot.
      </p>
    );
  }

  if (usable.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No scored assignments in this series yet. Once attempts complete and
        score, a line per competency lands here.
      </p>
    );
  }

  // Determine the x-axis domain from the union of sequence numbers across
  // every competency line. Empty fallback keeps the SVG renderable.
  const allSeq = usable.flatMap((l) => l.points.map((p) => p.sequence_number));
  const minSeq = Math.min(...allSeq);
  const maxSeq = Math.max(...allSeq);
  const spanSeq = Math.max(1, maxSeq - minSeq);

  const W = 640;
  const H = 220;
  const padL = 36;
  const padR = 16;
  const padT = 12;
  const padB = 28;
  const innerW = W - padL - padR;
  const innerH = H - padT - padB;

  const xFor = (seq: number) => padL + ((seq - minSeq) / spanSeq) * innerW;
  const yFor = (pct: number) =>
    padT + (1 - Math.max(0, Math.min(100, pct)) / 100) * innerH;

  return (
    <div className="text-foreground">
      <svg
        aria-labelledby="series-trend-title"
        height={H}
        role="img"
        viewBox={`0 0 ${W} ${H}`}
        width="100%"
        xmlns="http://www.w3.org/2000/svg"
      >
        <title id="series-trend-title">
          Competency score trend by sequence number
        </title>
        {/* gridlines + axis labels (0, 25, 50, 75, 100) */}
        {[0, 25, 50, 75, 100].map((tick) => {
          const y = yFor(tick);
          return (
            <g key={`grid-${tick}`}>
              <line
                stroke="currentColor"
                strokeOpacity={0.1}
                strokeWidth={1}
                x1={padL}
                x2={W - padR}
                y1={y}
                y2={y}
              />
              <text
                className="text-muted-foreground"
                dominantBaseline="middle"
                fill="currentColor"
                fontSize={10}
                textAnchor="end"
                x={padL - 6}
                y={y}
              >
                {tick}%
              </text>
            </g>
          );
        })}

        {/* x-axis ticks: one per integer sequence number, capped at 12 */}
        {(() => {
          const span = maxSeq - minSeq;
          const stepSeq = Math.max(1, Math.ceil((span + 1) / 12));
          const ticks: number[] = [];
          for (let s = minSeq; s <= maxSeq; s += stepSeq) {
            ticks.push(s);
          }
          if (ticks.at(-1) !== maxSeq) {
            ticks.push(maxSeq);
          }
          return ticks.map((s) => (
            <text
              className="text-muted-foreground"
              fill="currentColor"
              fontSize={10}
              key={`xtick-${s}`}
              textAnchor="middle"
              x={xFor(s)}
              y={H - 10}
            >
              #{s}
            </text>
          ));
        })()}

        {usable.map((line, idx) => {
          const color = TREND_COLORS[idx % TREND_COLORS.length];
          const sorted = [...line.points].sort(
            (a, b) => a.sequence_number - b.sequence_number
          );
          const path = sorted
            .filter((p) => p.score_pct != null)
            .map((p, i) => {
              const x = xFor(p.sequence_number);
              const y = yFor(p.score_pct ?? 0);
              return `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`;
            })
            .join(" ");
          return (
            <g key={line.competency_id}>
              <path
                d={path}
                fill="none"
                stroke={color}
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
              />
              {sorted
                .filter((p) => p.score_pct != null)
                .map((p) => (
                  <circle
                    cx={xFor(p.sequence_number)}
                    cy={yFor(p.score_pct ?? 0)}
                    fill={color}
                    key={`pt-${line.competency_id}-${p.sequence_number}`}
                    r={3}
                  />
                ))}
            </g>
          );
        })}
      </svg>

      <ul className="mt-2 flex flex-wrap gap-3 text-xs">
        {usable.map((line, idx) => (
          <li
            className="inline-flex items-center gap-1.5"
            key={`legend-${line.competency_id}`}
          >
            <span
              aria-hidden="true"
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{
                backgroundColor: TREND_COLORS[idx % TREND_COLORS.length],
              }}
            />
            <span>{line.competency_id}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}
