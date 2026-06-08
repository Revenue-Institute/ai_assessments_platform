"use client";

import { useFormStatus } from "react-dom";

export function SubmitButton({
  children,
  pendingLabel,
  className = "btn-primary w-full",
  disabled: externalDisabled,
  title,
}: {
  children: React.ReactNode;
  pendingLabel?: string;
  className?: string;
  disabled?: boolean;
  title?: string;
}) {
  const { pending } = useFormStatus();
  return (
    <button
      className={`${className} disabled:opacity-60 disabled:cursor-not-allowed`}
      disabled={pending || externalDisabled}
      title={title}
      type="submit"
    >
      {pending && pendingLabel ? pendingLabel : children}
    </button>
  );
}
