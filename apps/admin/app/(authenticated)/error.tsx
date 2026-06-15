"use client";

import { useEffect } from "react";

export default function ErrorBoundary({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-4 p-8 text-center">
      <div className="flex flex-col gap-2">
        <h2 className="font-semibold text-lg">Something went wrong</h2>
        <p className="max-w-sm text-muted-foreground text-sm">
          {error.message ||
            "An unexpected error occurred. Try again or contact support if the problem persists."}
        </p>
        {error.digest && (
          <p className="font-mono text-muted-foreground/60 text-xs">
            ID: {error.digest}
          </p>
        )}
      </div>
      <button
        className="inline-flex items-center rounded-md bg-primary px-4 py-2 font-medium text-primary-foreground text-sm transition-colors hover:bg-primary/90"
        onClick={reset}
        type="button"
      >
        Try again
      </button>
    </div>
  );
}
