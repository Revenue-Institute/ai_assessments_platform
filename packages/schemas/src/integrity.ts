import { z } from "zod";

export const IntegrityEventType = z.enum([
  "attempt_started",
  "question_served",
  "focus_gained",
  "focus_lost",
  "visibility_hidden",
  "visibility_visible",
  "fullscreen_entered",
  "fullscreen_exited",
  "copy_attempted",
  "cut_attempted",
  "paste_attempted",
  "context_menu_opened",
  "keyboard_shortcut_blocked",
  "window_resized",
  "devtools_opened",
  "network_offline",
  "network_online",
  "interactive_state_saved",
  "code_executed",
  "test_run",
  "n8n_workflow_saved",
  "notebook_cell_run",
  "question_submitted",
  "attempt_submitted",
]);
export type IntegrityEventType = z.infer<typeof IntegrityEventType>;

export const IntegrityEvent = z.object({
  type: IntegrityEventType,
  payload: z.record(z.string(), z.any()).default({}),
  client_timestamp: z.string().datetime().optional(),
});
export type IntegrityEvent = z.infer<typeof IntegrityEvent>;
