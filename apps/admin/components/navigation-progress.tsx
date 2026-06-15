"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

type Phase = "idle" | "loading" | "done";

export function NavigationProgress() {
  const pathname = usePathname();
  const [phase, setPhase] = useState<Phase>("idle");
  const currentPath = useRef(pathname);
  const doneTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Keep ref in sync and detect navigation completion
  useEffect(() => {
    if (pathname !== currentPath.current) {
      currentPath.current = pathname;
      if (phase === "loading") {
        setPhase("done");
        doneTimer.current = setTimeout(() => setPhase("idle"), 400);
      }
    }
    return () => {
      if (doneTimer.current) {
        clearTimeout(doneTimer.current);
      }
    };
  }, [pathname, phase]);

  useEffect(() => {
    function onMouseDown(e: MouseEvent) {
      const anchor = (e.target as Element).closest("a[href]");
      if (!anchor) {
        return;
      }
      const href = anchor.getAttribute("href") ?? "";
      if (
        !href ||
        href.startsWith("#") ||
        href.startsWith("http") ||
        href.startsWith("mailto:")
      ) {
        return;
      }
      // Skip if clicking the current page (pathname won't change so bar would loop forever)
      if (href === currentPath.current) {
        return;
      }
      setPhase("loading");
    }
    document.addEventListener("mousedown", onMouseDown);
    return () => document.removeEventListener("mousedown", onMouseDown);
  }, []);

  if (phase === "idle") {
    return null;
  }

  return (
    <div
      aria-hidden="true"
      className="fixed top-0 left-0 z-50 h-[2px] w-full overflow-hidden bg-primary/20"
    >
      {phase === "loading" && (
        <div
          className="h-full w-1/3 bg-primary"
          style={{ animation: "nav-progress 1.5s ease-in-out infinite" }}
        />
      )}
      {phase === "done" && (
        <div
          className="h-full w-full bg-primary"
          style={{ animation: "nav-progress-fade 400ms ease-out forwards" }}
        />
      )}
    </div>
  );
}
