"use client";

import { useFormStatus } from "react-dom";

const inputClass =
  "w-full rounded border border-border/60 bg-background px-3 py-2 text-sm focus:border-primary focus:outline-none";

export function EnrollForm({
  action,
  error,
}: {
  action: (formData: FormData) => Promise<void>;
  error?: string;
}) {
  return (
    <>
      {error && (
        <p
          aria-live="assertive"
          className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
          role="alert"
        >
          {error}
        </p>
      )}
      <form action={action} className="space-y-4">
        <label className="block space-y-1">
          <span className="font-medium text-sm">Full name</span>
          <input
            autoComplete="name"
            className={inputClass}
            name="full_name"
            placeholder="Jane Doe"
            required
          />
        </label>
        <label className="block space-y-1">
          <span className="font-medium text-sm">Email</span>
          <input
            autoComplete="email"
            className={inputClass}
            name="email"
            placeholder="jane@company.com"
            required
            type="email"
          />
        </label>
        <label className="flex items-start gap-2 text-muted-foreground text-sm">
          <input
            className="mt-1"
            defaultChecked
            name="consent"
            type="checkbox"
          />
          <span>
            I agree to begin this assessment. The session is timed and monitored
            for integrity; full details are shown on the next screen before any
            questions appear.
          </span>
        </label>
        <SubmitButton />
      </form>
    </>
  );
}

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-60"
      disabled={pending}
      type="submit"
    >
      {pending ? "Starting..." : "Start assessment"}
    </button>
  );
}
