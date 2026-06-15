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
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-3 px-6 text-center">
      <h1 className="font-semibold text-2xl">Something went wrong</h1>
      <p className="text-muted-foreground text-sm">
        {error.message ||
          "An unexpected error occurred. Please refresh the page or contact support."}
      </p>
      {error.digest && (
        <p className="font-mono text-muted-foreground/60 text-xs">
          ID: {error.digest}
        </p>
      )}
      <button
        className="mt-2 rounded bg-primary px-4 py-2 font-medium text-primary-foreground text-sm transition-colors hover:bg-primary/90"
        onClick={reset}
        type="button"
      >
        Try again
      </button>
    </main>
  );
}
