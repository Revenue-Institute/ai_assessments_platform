"use client";

import { emitIntegrityEvent } from "@repo/integrity/browser";

/** Client-side submit button. Wraps the server action's submit so we can
 * emit the spec §5.3 lifecycle events (`question_submitted` on every
 * submit, `attempt_submitted` additionally on the last question's submit)
 * synchronously before the form's POST kicks off. The integrity sink is
 * the same batched queue the candidate-monitor flushes every 2s, so we
 * do not need to await any network call here. */
export function SubmitButton({
  last,
  assignmentId,
  questionIndex,
}: {
  last: boolean;
  assignmentId: string;
  questionIndex: number;
}) {
  function onClick() {
    emitIntegrityEvent("question_submitted", {
      assignment_id: assignmentId,
      question_index: questionIndex,
    });
    if (last) {
      emitIntegrityEvent("attempt_submitted", {
        assignment_id: assignmentId,
      });
    }
  }

  return (
    <button className="btn-primary w-full" onClick={onClick} type="submit">
      {last ? "Submit and finish" : "Save and continue"}
    </button>
  );
}
