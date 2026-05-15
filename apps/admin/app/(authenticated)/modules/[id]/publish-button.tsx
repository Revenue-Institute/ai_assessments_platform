"use client";

import { useTransition } from "react";

export interface PreflightIssue {
  message: string;
}

export function PublishButton({
  action,
  issues,
}: {
  action: () => Promise<void>;
  issues: PreflightIssue[];
}) {
  const [pending, startTransition] = useTransition();
  const disabled = issues.length > 0 || pending;
  const title =
    issues.length > 0
      ? issues.map((i) => `- ${i.message}`).join("\n")
      : "Publish this module. Backend re-validates before flipping status.";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        if (disabled) {
          return;
        }
        startTransition(async () => {
          await action();
        });
      }}
    >
      <button
        aria-describedby={issues.length > 0 ? "publish-issues" : undefined}
        className="btn-primary text-sm disabled:cursor-not-allowed disabled:opacity-60"
        disabled={disabled}
        title={title}
        type="submit"
      >
        {pending ? "Publishing..." : "Publish"}
      </button>
      {issues.length > 0 && (
        <ul
          className="mt-2 max-w-md list-disc space-y-0.5 pl-5 text-destructive text-xs"
          id="publish-issues"
        >
          {issues.map((issue) => (
            <li key={issue.message}>{issue.message}</li>
          ))}
        </ul>
      )}
    </form>
  );
}
