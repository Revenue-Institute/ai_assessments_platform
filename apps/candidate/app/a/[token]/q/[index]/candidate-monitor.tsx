"use client";

import {
  emitIntegrityEvent,
  type IntegrityEvent,
  installIntegrityMonitor,
} from "@repo/integrity/browser";
import { useCallback, useEffect, useRef, useState } from "react";
import { env } from "@/env";

const HEARTBEAT_INTERVAL_MS = 10_000;
const EVENTS_FLUSH_MS = 2000;
const FULLSCREEN_GRACE_MS = 3000;
const TRAILING_SLASH_RE = /\/$/;

/** Mounts the spec §10.2 browser monitor and runs a 10s heartbeat that
 * reports focused-seconds back to FastAPI. Lives inside the question page
 * so it auto-tears down on navigation.
 *
 * Also enforces fullscreen per spec §10.3: on first mount surfaces an
 * "Enter fullscreen" banner if the page isn't already fullscreen, and on
 * fullscreen_exited (after a 3s grace) shows a blocking modal asking
 * the candidate to return to fullscreen.
 *
 * Spec §5.3 attempt lifecycle events: emits `attempt_started` once per
 * assignment (deduped via sessionStorage so navigating between questions
 * does not refire it) and `question_served` on every question mount. */
export function CandidateMonitor({
  token,
  assignmentId,
  questionIndex,
}: {
  token: string;
  assignmentId: string;
  questionIndex: number;
}) {
  const queueRef = useRef<IntegrityEvent[]>([]);
  const focusedSecondsRef = useRef(0);
  const lastTickRef = useRef(Date.now());
  const isFocusedRef = useRef(true);
  // Initialized inside the first useEffect so React StrictMode's double-mount
  // does not leak a stale mountedAt across unmount/remount cycles.
  const mountedAtRef = useRef(0);

  const [isFullscreen, setIsFullscreen] = useState(false);
  const [showExitModal, setShowExitModal] = useState(false);
  const modalReturnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    mountedAtRef.current = Date.now();
    isFocusedRef.current = !document.hidden && document.hasFocus();
    setIsFullscreen(Boolean(document.fullscreenElement));

    const apiBase = env.NEXT_PUBLIC_API_URL.replace(TRAILING_SLASH_RE, "");
    const eventsUrl = `${apiBase}/a/${encodeURIComponent(token)}/events`;
    const heartbeatUrl = `${apiBase}/a/${encodeURIComponent(token)}/heartbeat`;

    const flushEvents = async () => {
      if (queueRef.current.length === 0) {
        return;
      }
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
      if (focused === 0) {
        return;
      }
      // Snapshot the accumulator BEFORE the network call. If the request
      // fails we add the snapshot back so seconds aren't silently dropped
      // (matters most on flaky networks where every heartbeat retries).
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
        // Server-side deadline is authoritative; restore the focused
        // seconds so the next heartbeat picks them up.
        focusedSecondsRef.current += focused;
      }
    };

    const teardown = installIntegrityMonitor({
      send: (event) => {
        queueRef.current.push(event);
        if (event.type === "focus_lost" || event.type === "visibility_hidden") {
          isFocusedRef.current = false;
        }
        if (
          event.type === "focus_gained" ||
          event.type === "visibility_visible"
        ) {
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

    // Spec §5.3 attempt lifecycle. Fire AFTER installIntegrityMonitor so
    // the events land on the active sink (which the install call binds).
    // `attempt_started` is deduped per assignment via sessionStorage so
    // refreshing or navigating between questions does not retrigger it.
    // `question_served` fires unconditionally on every question mount.
    try {
      const attemptStartedKey = `ri:attempt_started:${assignmentId}`;
      const alreadyStarted = sessionStorage.getItem(attemptStartedKey) === "1";
      if (!alreadyStarted) {
        emitIntegrityEvent("attempt_started", { assignment_id: assignmentId });
        sessionStorage.setItem(attemptStartedKey, "1");
      }
    } catch {
      // sessionStorage can throw in private browsing; emit anyway so we
      // never silently drop the spec §5.3 event.
      emitIntegrityEvent("attempt_started", { assignment_id: assignmentId });
    }
    emitIntegrityEvent("question_served", {
      assignment_id: assignmentId,
      question_index: questionIndex,
    });

    const flushTimer = setInterval(flushEvents, EVENTS_FLUSH_MS);
    const heartbeatTimer = setInterval(sendHeartbeat, HEARTBEAT_INTERVAL_MS);

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
      clearInterval(flushTimer);
      clearInterval(heartbeatTimer);
      window.removeEventListener("beforeunload", onUnload);
      flushEvents();
      sendHeartbeat();
    };
  }, [token, assignmentId, questionIndex]);

  const enterFullscreen = useCallback(async () => {
    try {
      await document.documentElement.requestFullscreen();
    } catch {
      // Some browsers throw on iframes / permission denial. The integrity
      // event log will record either way.
    }
  }, []);

  // Spec §10.3 + WCAG 2.1.2: when the blocking modal opens, capture the
  // previously focused element so we can restore focus on close, and
  // intercept Escape so the user can re-enter fullscreen via keyboard
  // alone. Tab is intercepted to keep focus on the single button (focus
  // trap; the modal has only one focusable element).
  useEffect(() => {
    if (!showExitModal) {
      return;
    }
    modalReturnFocusRef.current = document.activeElement as HTMLElement | null;
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        enterFullscreen();
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
  }, [showExitModal, enterFullscreen]);

  return (
    <>
      {!isFullscreen && (
        <output className="flex items-center justify-between gap-3 rounded border border-warning/40 bg-warning/10 px-3 py-2 text-warning text-xs">
          <span>This assessment runs in fullscreen. Exits are logged.</span>
          <button
            className="rounded bg-warning px-2 py-1 font-medium text-warning-foreground hover:opacity-90"
            onClick={enterFullscreen}
            type="button"
          >
            Enter fullscreen
          </button>
        </output>
      )}

      {showExitModal && (
        <div
          aria-labelledby="fs-modal-title"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
          role="dialog"
        >
          <div className="max-w-md animate-reveal rounded border border-warning/40 bg-card p-6 text-center shadow-xl">
            <h2
              className="font-semibold text-lg text-warning"
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
