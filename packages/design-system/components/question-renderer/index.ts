/**
 * Shared question renderers for the static (non-sandbox) question
 * types: mcq, multi_select, short_answer, long_answer, scenario.
 *
 * The interactive-sandbox renderers (code, sql, notebook, diagram, n8n)
 * stay in each consuming app because they depend on Monaco / React
 * Flow / n8n iframe / E2B fetch wiring that we deliberately keep out
 * of the shared design-system surface.
 */

export { LongAnswerRenderer } from "./long-answer";
export { McqRenderer } from "./mcq";
export { MultiSelectRenderer } from "./multi-select";
export { ScenarioRenderer } from "./scenario";
export { ShortAnswerRenderer } from "./short-answer";
export type { QuestionForRenderer, QuestionRendererMode } from "./types";
