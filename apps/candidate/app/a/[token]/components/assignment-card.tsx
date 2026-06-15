import type { CandidateAssignmentView } from "@/lib/api";

export function AssignmentCard({
  assignment,
}: {
  assignment: CandidateAssignmentView;
}) {
  return (
    <dl className="grid grid-cols-2 gap-3 rounded border border-border bg-card p-5 text-sm">
      <div>
        <dt className="eyebrow-label">Candidate</dt>
        <dd className="mt-1 font-medium">{assignment.subject.full_name}</dd>
      </div>
      <div>
        <dt className="eyebrow-label">Time limit</dt>
        <dd className="mt-1 font-medium">
          {assignment.module.target_duration_minutes} minutes
        </dd>
      </div>
      <div>
        <dt className="eyebrow-label">Questions</dt>
        <dd className="mt-1 font-medium">{assignment.module.question_count}</dd>
      </div>
      <div>
        <dt className="eyebrow-label">Link expires</dt>
        <dd className="mt-1 font-medium">
          {new Date(assignment.expires_at).toLocaleString()}
        </dd>
      </div>
    </dl>
  );
}
