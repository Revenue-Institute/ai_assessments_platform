type Slice = {
  competency_id: string;
  score_pct: number;
};

const SIZE = 320;
const PADDING = 60;
const RADIUS = SIZE / 2 - PADDING;
const RINGS = 5;

export function CompetencyRadar({ slices }: { slices: Slice[] }) {
  if (slices.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center rounded-xl border border-border/50 bg-muted/20 text-muted-foreground text-sm">
        No competency scores yet — complete an assessment first.
      </div>
    );
  }

  const cx = SIZE / 2;
  const cy = SIZE / 2;
  const angleStep = (Math.PI * 2) / slices.length;

  const polygonPoints = slices
    .map((slice, i) => {
      const angle = -Math.PI / 2 + angleStep * i;
      const r = (Math.max(0, Math.min(100, slice.score_pct)) / 100) * RADIUS;
      const x = cx + Math.cos(angle) * r;
      const y = cy + Math.sin(angle) * r;
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  return (
    <div className="rounded-xl border border-border/50 bg-muted/20 p-4 text-primary">
      <svg
        height={SIZE}
        viewBox={`0 0 ${SIZE} ${SIZE}`}
        width={SIZE}
        xmlns="http://www.w3.org/2000/svg"
      >
        {/* concentric rings */}
        {Array.from({ length: RINGS }, (_, i) => {
          const r = ((i + 1) / RINGS) * RADIUS;
          return (
            <circle
              cx={cx}
              cy={cy}
              fill="none"
              key={`ring-${i}`}
              r={r}
              stroke="currentColor"
              strokeOpacity={0.1}
              strokeWidth={1}
            />
          );
        })}

        {/* axes */}
        {slices.map((slice, i) => {
          const angle = -Math.PI / 2 + angleStep * i;
          const x = cx + Math.cos(angle) * RADIUS;
          const y = cy + Math.sin(angle) * RADIUS;
          return (
            <line
              key={`axis-${slice.competency_id}`}
              stroke="currentColor"
              strokeOpacity={0.15}
              strokeWidth={1}
              x1={cx}
              x2={x}
              y1={cy}
              y2={y}
            />
          );
        })}

        {/* radar polygon */}
        <polygon
          fill="currentColor"
          fillOpacity={0.25}
          points={polygonPoints}
          stroke="currentColor"
          strokeLinejoin="round"
          strokeWidth={2}
        />

        {/* point markers */}
        {slices.map((slice, i) => {
          const angle = -Math.PI / 2 + angleStep * i;
          const r =
            (Math.max(0, Math.min(100, slice.score_pct)) / 100) * RADIUS;
          const x = cx + Math.cos(angle) * r;
          const y = cy + Math.sin(angle) * r;
          return (
            <circle
              cx={x}
              cy={y}
              fill="currentColor"
              key={`pt-${slice.competency_id}`}
              r={3}
            />
          );
        })}

        {/* labels */}
        {slices.map((slice, i) => {
          const angle = -Math.PI / 2 + angleStep * i;
          const labelDistance = RADIUS + 20;
          const x = cx + Math.cos(angle) * labelDistance;
          const y = cy + Math.sin(angle) * labelDistance;
          const anchor =
            Math.cos(angle) > 0.3
              ? "start"
              : Math.cos(angle) < -0.3
                ? "end"
                : "middle";
          const tag = displayTag(slice.competency_id);
          return (
            <g key={`label-${slice.competency_id}`}>
              <text
                className="text-foreground"
                dominantBaseline="middle"
                fill="currentColor"
                fillOpacity={0.7}
                fontSize={10}
                textAnchor={anchor}
                x={x}
                y={y}
              >
                {tag}
              </text>
              <text
                className="text-primary"
                dominantBaseline="middle"
                fill="currentColor"
                fontSize={10}
                textAnchor={anchor}
                x={x}
                y={y + 12}
              >
                {Math.round(slice.score_pct)}%
              </text>
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function displayTag(id: string): string {
  const last = id.split(".").pop() ?? id;
  return last.replace(/_/g, " ");
}
