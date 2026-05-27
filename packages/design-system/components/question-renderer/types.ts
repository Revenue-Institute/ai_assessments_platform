/**
 * Shared shape for the static question renderers (mcq, multi_select,
 * short_answer, long_answer, scenario). Both apps narrow their own
 * question type to this when calling the shared renderers:
 *
 *   - apps/candidate passes its CandidateQuestionView with a populated
 *     raw_answer (for "resume in progress" UX)
 *   - apps/admin passes its ModulePreviewQuestion (raw_answer is always
 *     undefined; preview mode never has a candidate response yet)
 *
 * The renderer reads only `type`, `interactive_config`, and
 * `raw_answer?.value`. Anything outside that surface stays in the
 * caller's app-local type.
 *
 * `mode="interactive"` produces a real form input (the candidate's
 * runtime experience). `mode="preview"` disables every input + drops
 * required so an admin can scroll the bank without form-submit noise.
 */
export type QuestionRendererMode = "interactive" | "preview";

export interface QuestionForRenderer {
  type: string;
  interactive_config?: Record<string, unknown> | null;
  raw_answer?: { value?: unknown } | null;
}
