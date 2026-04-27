"use client";

import { CheckIcon, CopyIcon } from "lucide-react";
import { useState } from "react";

/** Tiny copy-to-clipboard button. Shows a check mark for ~1.5s after a
 * successful copy. Falls back silently if the clipboard API is
 * unavailable (older browsers, insecure context). */
export function CopyButton({
  value,
  label = "Copy",
  className,
}: {
  value: string;
  label?: string;
  className?: string;
}) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard API unavailable; user can still select + copy by hand.
    }
  }

  return (
    <button
      aria-live="polite"
      className={
        className ??
        "inline-flex items-center gap-1 rounded border border-border bg-card px-2 py-1 text-xs hover:bg-primary/10"
      }
      onClick={copy}
      title={copied ? "Copied" : label}
      type="button"
    >
      {copied ? (
        <CheckIcon aria-hidden="true" className="h-3.5 w-3.5 text-primary" />
      ) : (
        <CopyIcon aria-hidden="true" className="h-3.5 w-3.5" />
      )}
      <span>{copied ? "Copied" : label}</span>
    </button>
  );
}
