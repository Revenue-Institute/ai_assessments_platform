"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

export function AutoRedirect({
  href,
  message,
  seconds = 3,
}: {
  href: string;
  message: string;
  seconds?: number;
}) {
  const router = useRouter();
  const [remaining, setRemaining] = useState(seconds);

  useEffect(() => {
    if (remaining <= 0) {
      router.push(href);
      return;
    }
    const t = setTimeout(() => setRemaining((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [remaining, href, router]);

  return (
    <p
      aria-live="assertive"
      className="rounded border border-destructive/50 bg-destructive/15 px-3 py-2 text-destructive text-sm"
      role="alert"
    >
      {message} Continuing in {remaining}s...
    </p>
  );
}
