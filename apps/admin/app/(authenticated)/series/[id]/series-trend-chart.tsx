import type { SeriesTrendLine, SeriesTrendResponse } from "@/lib/api";

interface SeriesTrendChartProps {
  focus: string[];
  trend: SeriesTrendResponse | null;
}

// Brand-leaning palette, hand-picked for distinguishability in both themes; cycled when focus list exceeds array length.
const TREND_COLORS = [
  "rgb(10 143 93)", // brand forest
  "rgb(56 189 248)", // sky
  "rgb(217 119 6)", // amber
  "rgb(244 63 94)", // rose
  "rgb(167 139 250)", // violet
  "rgb(45 212 191)", // teal
];

export function SeriesTrendChart({ focus, trend }: SeriesTrendChartProps) {
  const lines: SeriesTrendLine[] = Array.isArray(trend?.trends) ? trend.trends : [];
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

  // x-axis domain: union of sequence numbers across all lines; empty fallback keeps the SVG renderable.
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

  const span = maxSeq - minSeq;
  const stepSeq = Math.max(1, Math.ceil((span + 1) / 12));
  const xTicks: number[] = [];
  for (let s = minSeq; s <= maxSeq; s += stepSeq) xTicks.push(s);
  if (xTicks.at(-1) !== maxSeq) xTicks.push(maxSeq);

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
        {xTicks.map((s) => (
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
        ))}

        {usable.map((line, idx) => {
          const color = TREND_COLORS[idx % TREND_COLORS.length];
          const sorted = [...line.points].sort(
            (a, b) => a.sequence_number - b.sequence_number
          );
          const coords = sorted
            .filter((p) => p.score_pct != null)
            .map((p) => ({
              x: xFor(p.sequence_number),
              y: yFor(p.score_pct ?? 0),
              seq: p.sequence_number,
            }));
          const path = coords
            .map(({ x, y }, i) => `${i === 0 ? "M" : "L"} ${x.toFixed(1)} ${y.toFixed(1)}`)
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
              {coords.map(({ x, y, seq }) => (
                <circle
                  cx={x}
                  cy={y}
                  fill={color}
                  key={`pt-${line.competency_id}-${seq}`}
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
