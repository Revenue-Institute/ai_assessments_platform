"use client";

import { useEffect } from "react";

/** Wires a `beforeunload` guard so the browser warns the candidate
 * before navigating away when `dirty` is true.
 *
 * Modern browsers ignore the custom message (the dialog text is
 * browser-controlled), but the confirmation prompt itself still appears,
 * which is enough to prevent accidental loss of in-flight code, sql, or
 * notebook work.
 *
 * **Important nuance:** form submissions also trigger `beforeunload` in
 * most browsers, so without intervention the candidate's "Save and
 * continue" button would prompt "are you sure you want to leave?". We
 * suppress the guard the moment any form on the page begins submitting
 * — that submission is the candidate's intentional save. */
export function useUnsavedChangesWarning(dirty: boolean): void {
  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      // Older browsers required returnValue to be set; modern ones just
      // need preventDefault. Setting both is harmless and most compat.
      e.returnValue = "";
    };
    const onFormSubmit = () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    document.addEventListener("submit", onFormSubmit, true);
    return () => {
      window.removeEventListener("beforeunload", onBeforeUnload);
      document.removeEventListener("submit", onFormSubmit, true);
    };
  }, [dirty]);
}
