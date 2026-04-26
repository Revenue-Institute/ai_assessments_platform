"use client";

import {
  installIntegrityMonitor,
  type IntegrityEvent,
} from "@repo/integrity/browser";
import { useEffect, useRef } from "react";
import { env } from "@/env";

const HEARTBEAT_INTERVAL_MS = 10_000;
const EVENTS_FLUSH_MS = 2_000;

/** Mounts the spec §10.2 browser monitor and runs a 10s heartbeat that
 * reports focused-seconds back to FastAPI. Lives inside the question page
 * so it auto-tears down on navigation. */
export function CandidateMonitor({ token }: { token: string }) {
  const queueRef = useRef<IntegrityEvent[]>([]);
  const focusedSecondsRef = useRef(0);
  const lastTickRef = useRef<number>(Date.now());
  const isFocusedRef = useRef<boolean>(true);

  useEffect(() => {
    if (typeof document !== "undefined") {
      isFocusedRef.current = !document.hidden && document.hasFocus();
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
        // Re-queue on transport failure so we try again next tick.
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
        // Best-effort. Server-side deadline is authoritative.
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
      },
    });

    const flushTimer = window.setInterval(flushEvents, EVENTS_FLUSH_MS);
    const heartbeatTimer = window.setInterval(
      sendHeartbeat,
      HEARTBEAT_INTERVAL_MS
    );

    const onUnload = () => {
      // Best-effort flush before navigating away.
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

  return null;
}
