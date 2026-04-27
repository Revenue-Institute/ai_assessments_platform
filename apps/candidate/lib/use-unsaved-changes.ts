"use client";

import { useEffect } from "react";

/** Wires a `beforeunload` guard so the browser warns the candidate
 * before navigating away when `dirty` is true. Modern browsers ignore
 * the custom message — the dialog text is browser-controlled — but the
 * confirmation prompt itself still appears, which is enough to prevent
 * accidental loss of in-flight code, sql, or notebook work. */
export function useUnsavedChangesWarning(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Older browsers required returnValue to be set; modern ones just
      // need preventDefault. Setting both is harmless and most compat.
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);
}
