type Stats = {
  min_pct: number;
  p25_pct: number;
  median_pct: number;
  p75_pct: number;
  max_pct: number;
  sample_size: number;
};

type Props = {
  stats: Stats;
  candidateScore: number;
  width?: number;
  height?: number;
};

/** Compact horizontal box-plot — whiskers from min→max, IQR box, median tick,
 * and a marker for the candidate's score (spec §11.3). Falls back to a flat
 * line when the cohort has < 2 samples. */
export function DistributionBox({
  stats,
  candidateScore,
  width = 240,
  height = 28,
}: Props) {
  if (stats.sample_size === 0) {
    return (
      <p className="text-muted-foreground text-[11px]">No team data yet.</p>
    );
  }
  const padX = 2;
  const trackY = height / 2;
  const x = (pct: number) =>
    padX + (Math.max(0, Math.min(100, pct)) / 100) * (width - padX * 2);

  const minX = x(stats.min_pct);
  const maxX = x(stats.max_pct);
  const p25X = x(stats.p25_pct);
  const p75X = x(stats.p75_pct);
  const medX = x(stats.median_pct);
  const candX = x(candidateScore);

  const candidateAhead = candidateScore >= stats.median_pct;

  return (
    <div className="text-muted-foreground">
      <svg
        aria-hidden="true"
        height={height}
        viewBox={`0 0 ${width} ${height}`}
        width={width}
      >
        {/* track grid */}
        <line
          stroke="currentColor"
          strokeOpacity={0.1}
          strokeWidth={1}
          x1={padX}
          x2={width - padX}
          y1={trackY}
          y2={trackY}
        />
        {/* whisker */}
        <line
          stroke="currentColor"
          strokeOpacity={0.5}
          strokeWidth={1}
          x1={minX}
          x2={maxX}
          y1={trackY}
          y2={trackY}
        />
        <line
          stroke="currentColor"
          strokeOpacity={0.5}
          strokeWidth={1}
          x1={minX}
          x2={minX}
          y1={trackY - 4}
          y2={trackY + 4}
        />
        <line
          stroke="currentColor"
          strokeOpacity={0.5}
          strokeWidth={1}
          x1={maxX}
          x2={maxX}
          y1={trackY - 4}
          y2={trackY + 4}
        />
        {/* IQR box */}
        <rect
          fill="currentColor"
          fillOpacity={0.18}
          height={12}
          stroke="currentColor"
          strokeWidth={1}
          width={Math.max(1, p75X - p25X)}
          x={p25X}
          y={trackY - 6}
        />
        {/* median */}
        <line
          stroke="currentColor"
          strokeWidth={2}
          x1={medX}
          x2={medX}
          y1={trackY - 6}
          y2={trackY + 6}
        />
        {/* candidate marker — primary if at/above median, destructive otherwise */}
        <circle
          className={candidateAhead ? "text-primary" : "text-destructive"}
          cx={candX}
          cy={trackY}
          fill="currentColor"
          r={5}
          stroke="var(--background)"
          strokeWidth={1}
        />
      </svg>
      <p className="text-[11px] text-muted-foreground">
        team n={stats.sample_size} · median {Math.round(stats.median_pct)}% ·
        IQR {Math.round(stats.p25_pct)}–{Math.round(stats.p75_pct)}% ·
        you {Math.round(candidateScore)}%
      </p>
    </div>
  );
}
