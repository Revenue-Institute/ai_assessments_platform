"use client";

import {
  installIntegrityMonitor,
  type IntegrityEvent,
} from "@repo/integrity/browser";
import { useEffect, useRef, useState } from "react";
import { env } from "@/env";

const HEARTBEAT_INTERVAL_MS = 10_000;
const EVENTS_FLUSH_MS = 2_000;
const FULLSCREEN_GRACE_MS = 3_000;

/** Mounts the spec §10.2 browser monitor and runs a 10s heartbeat that
 * reports focused-seconds back to FastAPI. Lives inside the question page
 * so it auto-tears down on navigation.
 *
 * Also enforces fullscreen per spec §10.3: on first mount surfaces an
 * "Enter fullscreen" banner if the page isn't already fullscreen, and on
 * fullscreen_exited (after a 3s grace) shows a blocking modal asking
 * the candidate to return to fullscreen. */
export function CandidateMonitor({ token }: { token: string }) {
  const queueRef = useRef<IntegrityEvent[]>([]);
  const focusedSecondsRef = useRef(0);
  const lastTickRef = useRef<number>(Date.now());
  const isFocusedRef = useRef<boolean>(true);
  const mountedAtRef = useRef<number>(Date.now());

  const [isFullscreen, setIsFullscreen] = useState<boolean>(false);
  const [showExitModal, setShowExitModal] = useState<boolean>(false);
  const modalReturnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (typeof document !== "undefined") {
      isFocusedRef.current = !document.hidden && document.hasFocus();
      setIsFullscreen(Boolean(document.fullscreenElement));
    }

    const apiBase = env.NEXT_PUBLIC_API_URL.replace(/\/$/, "");
    const eventsUrl = `${apiBase}/a/${encodeURIComponent(token)}/events`;
    const heartbeatUrl = `${apiBase}/a/${encodeURIComponent(token)}/heartbeat`;

    const flushEvents = async () => {
      if (queueRef.current.length === 0) return;
      const batch = queueRef.current;
      queueRef.current = [];
      try {
        await fetch(eventsUrl, {
          method: "POST",
          keepalive: true,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ events: batch }),
        });
      } catch {
        queueRef.current.unshift(...batch);
      }
    };

    const sendHeartbeat = async () => {
      const now = Date.now();
      const elapsed = (now - lastTickRef.current) / 1000;
      lastTickRef.current = now;
      if (isFocusedRef.current) {
        focusedSecondsRef.current += elapsed;
      }
      const focused = Math.min(120, Math.round(focusedSecondsRef.current));
      if (focused === 0) return;
      focusedSecondsRef.current = 0;
      try {
        await fetch(heartbeatUrl, {
          method: "POST",
          keepalive: true,
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            focused_seconds_since_last: focused,
          }),
        });
      } catch {
        // Server-side deadline is authoritative.
      }
    };

    const teardown = installIntegrityMonitor({
      send: (event) => {
        queueRef.current.push(event);
        if (event.type === "focus_lost" || event.type === "visibility_hidden") {
          isFocusedRef.current = false;
        }
        if (event.type === "focus_gained" || event.type === "visibility_visible") {
          isFocusedRef.current = true;
          lastTickRef.current = Date.now();
        }
        if (event.type === "fullscreen_entered") {
          setIsFullscreen(true);
          setShowExitModal(false);
        }
        if (event.type === "fullscreen_exited") {
          setIsFullscreen(false);
          // Spec §10.3: don't show on the first 3s in case the browser
          // auto-exits during navigation.
          if (Date.now() - mountedAtRef.current > FULLSCREEN_GRACE_MS) {
            setShowExitModal(true);
          }
        }
      },
    });

    const flushTimer = window.setInterval(flushEvents, EVENTS_FLUSH_MS);
    const heartbeatTimer = window.setInterval(
      sendHeartbeat,
      HEARTBEAT_INTERVAL_MS
    );

    const onUnload = () => {
      if (queueRef.current.length > 0) {
        navigator.sendBeacon?.(
          eventsUrl,
          new Blob([JSON.stringify({ events: queueRef.current })], {
            type: "application/json",
          })
        );
      }
    };
    window.addEventListener("beforeunload", onUnload);

    return () => {
      teardown();
      window.clearInterval(flushTimer);
      window.clearInterval(heartbeatTimer);
      window.removeEventListener("beforeunload", onUnload);
      flushEvents();
      sendHeartbeat();
    };
  }, [token]);

  const enterFullscreen = async () => {
    try {
      await document.documentElement.requestFullscreen();
    } catch {
      // Some browsers throw on iframes / permission denial. The integrity
      // event log will record either way.
    }
  };

  // Spec §10.3 + WCAG 2.1.2: when the blocking modal opens, capture the
  // previously focused element so we can restore focus on close, and
  // intercept Escape so the user can re-enter fullscreen via keyboard
  // alone. Tab is intercepted to keep focus on the single button (focus
  // trap; the modal has only one focusable element).
  useEffect(() => {
    if (!showExitModal) return;
    if (typeof document !== "undefined") {
      modalReturnFocusRef.current = (document.activeElement as HTMLElement) ?? null;
    }
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        void enterFullscreen();
      }
      if (e.key === "Tab") {
        e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      modalReturnFocusRef.current?.focus?.();
    };
  }, [showExitModal]);

  return (
    <>
      {!isFullscreen && (
        <div
          className="flex items-center justify-between gap-3 rounded border border-warning/40 bg-warning/10 px-3 py-2 text-warning text-xs"
          role="status"
        >
          <span>
            This assessment runs in fullscreen. Exits are logged.
          </span>
          <button
            className="rounded bg-warning px-2 py-1 font-medium text-warning-foreground hover:opacity-90"
            onClick={enterFullscreen}
            type="button"
          >
            Enter fullscreen
          </button>
        </div>
      )}

      {showExitModal && (
        <div
          aria-labelledby="fs-modal-title"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
          role="dialog"
        >
          <div className="max-w-md rounded border border-warning/40 bg-card p-6 text-center shadow-xl animate-reveal">
            <h2
              className="font-semibold text-warning text-lg"
              id="fs-modal-title"
            >
              Return to fullscreen to continue
            </h2>
            <p className="mt-2 text-muted-foreground text-sm">
              Your timer is still running and this exit has been logged.
              Re-enter fullscreen to dismiss this prompt.
            </p>
            <button
              autoFocus
              className="btn-primary mt-4"
              onClick={enterFullscreen}
              type="button"
            >
              Re-enter fullscreen
            </button>
          </div>
        </div>
      )}
    </>
  );
}
