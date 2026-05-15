/**
 * Single source of truth for color-tiered integrity score display.
 * Tiers (spec §10.4):
 *   85+   green   (primary)
 *   60-84 yellow  (warning)
 *   <60   red     (destructive)
 */

interface IntegrityScoreProps {
  className?: string;
  /** When true, render an ASCII hyphen for null/undefined instead of nothing. */
  fallback?: boolean;
  score: number | null | undefined;
}

export function IntegrityScore({
  score,
  fallback = false,
  className,
}: IntegrityScoreProps) {
  if (score == null) {
    return fallback ? <span className="text-muted-foreground">-</span> : null;
  }
  let tone = "text-destructive";
  if (score >= 85) {
    tone = "text-primary";
  } else if (score >= 60) {
    tone = "text-warning";
  }
  const cls = ["font-medium", tone, className].filter(Boolean).join(" ");
  const rounded = Math.round(score);
  return (
    <span className={cls} title={`Integrity score ${rounded} of 100`}>
      <span className="sr-only">Integrity score {rounded} of 100</span>
      <span aria-hidden="true">{rounded}</span>
    </span>
  );
}
