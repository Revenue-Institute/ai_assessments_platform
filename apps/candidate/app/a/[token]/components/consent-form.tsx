"use client";

import { useFormStatus } from "react-dom";

export function ConsentForm({
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
      <form action={action}>
        <ConsentSubmitButton />
      </form>
    </>
  );
}

function ConsentSubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      aria-describedby="monitor-heading"
      className="btn-primary w-full disabled:cursor-not-allowed disabled:opacity-60"
      disabled={pending}
      type="submit"
    >
      {pending ? "Starting..." : "I understand and consent to begin"}
    </button>
  );
}
