import type {
  CohortHeatmapResponse,
  CohortSubject,
} from "@/lib/api";

type Props = {
  data: CohortHeatmapResponse;
};

export function CompetencyHeatmap({ data }: Props) {
  if (
    data.subjects.length === 0 ||
    data.competencies.length === 0 ||
    data.cells.length === 0
  ) {
    return (
      <div className="rounded-xl border border-border/50 bg-muted/20 p-6 text-center text-muted-foreground text-sm">
        No scores in the current filter window. Have subjects complete some
        assessments to populate the heatmap.
      </div>
    );
  }

  const lookup = new Map<string, number>();
  for (const cell of data.cells) {
    lookup.set(cellKey(cell.subject_id, cell.competency_id), cell.score_pct);
  }

  return (
    <div className="overflow-auto rounded-xl border border-border/50 bg-muted/20">
      <table className="border-collapse text-xs">
        <thead className="sticky top-0 z-10 bg-muted text-left">
          <tr>
            <th className="sticky left-0 z-20 bg-muted px-3 py-2 font-medium">
              Subject
            </th>
            {data.competencies.map((c) => (
              <th
                className="border-border/30 border-l px-2 py-2 font-medium align-bottom"
                key={c}
              >
                <span
                  className="block whitespace-nowrap"
                  style={{ writingMode: "vertical-rl", transform: "rotate(180deg)" }}
                >
                  {tagShort(c)}
                </span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.subjects.map((subject) => (
            <tr
              className="border-border/30 border-t"
              key={subject.id}
            >
              <SubjectCell subject={subject} />
              {data.competencies.map((c) => {
                const score = lookup.get(cellKey(subject.id, c));
                return <ScoreCell key={c} score={score} />;
              })}
            </tr>
          ))}
          <tr className="border-border/40 border-t-2 bg-muted/40 font-medium">
            <td className="sticky left-0 bg-muted/40 px-3 py-2">
              Team avg
            </td>
            {data.competencies.map((c) => {
              const avg = data.team_average_pct[c];
              return <ScoreCell key={c} score={avg} />;
            })}
          </tr>
        </tbody>
      </table>
    </div>
  );
}

function SubjectCell({ subject }: { subject: CohortSubject }) {
  return (
    <td className="sticky left-0 z-10 max-w-[240px] bg-background px-3 py-2 align-middle">
      <p className="truncate font-medium">{subject.full_name}</p>
      <p className="truncate text-muted-foreground text-[11px]">
        {subject.email} · {subject.type}
      </p>
    </td>
  );
}

function ScoreCell({ score }: { score: number | undefined }) {
  if (score == null) {
    return (
      <td className="border-border/30 border-l px-2 py-2 text-muted-foreground">
        -
      </td>
    );
  }
  const bg = scoreColor(score);
  // High scores get a light foreground for contrast on darker greens;
  // low scores need dark text for AA contrast on the lighter amber/red mix.
  const fg = score >= 50 ? "rgb(248 250 252)" : "rgb(15 23 42)";
  return (
    <td
      className="border-border/30 border-l px-2 py-2 text-center font-medium"
      style={{ backgroundColor: bg, color: fg, minWidth: 56 }}
    >
      {Math.round(score)}
    </td>
  );
}

function cellKey(subjectId: string, competencyId: string): string {
  return `${subjectId}::${competencyId}`;
}

function tagShort(id: string): string {
  return id.split(".").slice(-2).join(".");
}

// Heatmap stop colors derive from the brand palette: deep red (destructive)
// at the low end, brand warning amber in the middle, brand forest green at
// the high end. Hardcoded rgb tuples here so we can interpolate; if the
// palette ever shifts these should be regenerated to match.
const STOP_LOW = "rgb(127 29 29)"; // dark destructive
const STOP_MID = "rgb(146 64 14)"; // dark warning
const STOP_HIGH = "rgb(10 143 93)"; // brand forest

function scoreColor(score: number): string {
  const clamped = Math.max(0, Math.min(100, score));
  const t = clamped / 100;
  if (t < 0.5) {
    const k = t / 0.5;
    return mix(STOP_LOW, STOP_MID, k);
  }
  const k = (t - 0.5) / 0.5;
  return mix(STOP_MID, STOP_HIGH, k);
}

function mix(a: string, b: string, t: number): string {
  const ra = parseRgb(a);
  const rb = parseRgb(b);
  const out = ra.map((v, i) => Math.round(v + (rb[i] - v) * t));
  return `rgb(${out.join(" ")})`;
}

function parseRgb(input: string): number[] {
  const m = input.match(/rgb\(([^)]+)\)/);
  if (!m) return [0, 0, 0];
  return m[1]
    .split(/[ ,]+/)
    .map((s) => Number.parseInt(s, 10))
    .slice(0, 3);
}
