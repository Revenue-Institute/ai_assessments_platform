import type { IntegrityEventType } from "@repo/schemas";

type EventCount = Partial<Record<IntegrityEventType, number>>;

type ScoreInput = {
  events: EventCount;
  /** Pastes whose payload.allowed === false. Pastes inside
   * data-allow-paste="true" code editors carry payload.allowed === true
   * and must be excluded; spec §10.4 only deducts for disallowed pastes. */
  paste_attempted_disallowed?: number;
  active_time_seconds: number;
  total_time_seconds: number;
};

/** Spec §10.4 integrity score formula. Higher is cleaner; floor at 0.
 *
 * The canonical computation lives in the FastAPI service (see
 * `apps/api/src/ri_assessments_api/services/scoring.py::_compute_integrity_score`).
 * This TS port exists so the admin UI can preview an in-progress score
 * before scoring lands; numbers must stay in lockstep with the Python
 * formula. */
export function computeIntegrityScore(input: ScoreInput): number {
  let score = 100;

  const visHidden = input.events.visibility_hidden ?? 0;
  if (visHidden > 3) score -= (visHidden - 3) * 3;

  const focusLost = input.events.focus_lost ?? 0;
  if (focusLost > 5) score -= (focusLost - 5) * 2;

  score -= (input.events.fullscreen_exited ?? 0) * 8;
  score -= (input.paste_attempted_disallowed ?? 0) * 5;
  score -= (input.events.copy_attempted ?? 0) * 2;
  if ((input.events.devtools_opened ?? 0) > 0) score -= 15;
  score -= (input.events.window_resized ?? 0) * 3;

  if (
    input.total_time_seconds > 0 &&
    input.active_time_seconds / input.total_time_seconds < 0.3
  ) {
    score -= 20;
  }

  return Math.max(0, Math.round(score * 100) / 100);
}
