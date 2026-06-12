import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import {
  type SeriesDetail,
  type SeriesTrendResponse,
  ApiError,
  getSeriesDetail,
  getSeriesTrend,
} from "@/lib/api";
import { AlertBanner } from "@/components/alert-banner";

import { Header } from "../../components/header";
import { SeriesTrendChart } from "./series-trend-chart";

export const dynamic = "force-dynamic";

type Params = Promise<{ id: string }>;

export async function generateMetadata({ params }: { params: Params }): Promise<Metadata> {
  const { id } = await params;
  try {
    const detail = await getSeriesDetail(id);
    return { title: detail.name };
  } catch {
    return { title: "Series" };
  }
}

export default async function SeriesDetailPage({ params }: { params: Params }) {
  const { id } = await params;

  const [detailResult, trendResult] = await Promise.allSettled([
    getSeriesDetail(id),
    getSeriesTrend(id),
  ]);

  if (detailResult.status === "rejected") {
    if (detailResult.reason instanceof ApiError && detailResult.reason.status === 404) {
      notFound();
    }
    throw detailResult.reason;
  }

  const detail: SeriesDetail = detailResult.value;

  // Trend is auxiliary: render the rest of the page even if the backend trend route is offline.
  const trend: SeriesTrendResponse | null =
    trendResult.status === "fulfilled" ? trendResult.value : null;
  const trendError: string | null =
    trendResult.status === "rejected"
      ? trendResult.reason instanceof ApiError
        ? trendResult.reason.message
        : "Could not load trend data."
      : null;

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
              <h2 className="font-semibold text-xl">{detail.name}</h2>
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
            <AlertBanner>{trendError}</AlertBanner>
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
