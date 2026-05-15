"use client";

import {
  ActivityIcon,
  AlertTriangleIcon,
  ClipboardCopyIcon,
  ClipboardPasteIcon,
  CodeIcon,
  EyeIcon,
  EyeOffIcon,
  FileEditIcon,
  KeyboardIcon,
  LayoutIcon,
  type LucideIcon,
  MaximizeIcon,
  MinimizeIcon,
  MousePointerClickIcon,
  PlayIcon,
  ScissorsIcon,
  SendIcon,
  TerminalIcon,
  WifiIcon,
  WifiOffIcon,
  WrenchIcon,
} from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { AttemptEvent } from "@/lib/api";

/**
 * Severity map keyed by the canonical integrity event taxonomy in
 * packages/schemas/src/integrity.ts. Anything missing here defaults to info.
 */
const SEVERITY: Record<string, "info" | "warn" | "alert"> = {
  attempt_started: "info",
  question_served: "info",
  focus_gained: "info",
  focus_lost: "warn",
  visibility_hidden: "warn",
  visibility_visible: "info",
  fullscreen_entered: "info",
  fullscreen_exited: "alert",
  copy_attempted: "warn",
  cut_attempted: "warn",
  paste_attempted: "alert",
  context_menu_opened: "info",
  keyboard_shortcut_blocked: "warn",
  window_resized: "warn",
  devtools_opened: "alert",
  network_offline: "warn",
  network_online: "info",
  interactive_state_saved: "info",
  code_executed: "info",
  test_run: "info",
  n8n_workflow_saved: "info",
  notebook_cell_run: "info",
  question_submitted: "info",
  attempt_submitted: "info",
};

const COLOR_BY_SEVERITY: Record<"info" | "warn" | "alert", string> = {
  info: "border-primary/40 bg-primary/10 text-primary",
  warn: "border-warning/50 bg-warning/15 text-warning",
  alert: "border-destructive/50 bg-destructive/15 text-destructive",
};

const DOT_BY_SEVERITY: Record<"info" | "warn" | "alert", string> = {
  info: "bg-primary",
  warn: "bg-warning",
  alert: "bg-destructive",
};

const ICON_BY_TYPE: Record<string, LucideIcon> = {
  attempt_started: PlayIcon,
  question_served: SendIcon,
  focus_gained: EyeIcon,
  focus_lost: EyeOffIcon,
  visibility_hidden: EyeOffIcon,
  visibility_visible: EyeIcon,
  fullscreen_entered: MaximizeIcon,
  fullscreen_exited: MinimizeIcon,
  copy_attempted: ClipboardCopyIcon,
  cut_attempted: ScissorsIcon,
  paste_attempted: ClipboardPasteIcon,
  context_menu_opened: MousePointerClickIcon,
  keyboard_shortcut_blocked: KeyboardIcon,
  window_resized: LayoutIcon,
  devtools_opened: WrenchIcon,
  network_offline: WifiOffIcon,
  network_online: WifiIcon,
  interactive_state_saved: FileEditIcon,
  code_executed: TerminalIcon,
  test_run: CodeIcon,
  n8n_workflow_saved: FileEditIcon,
  notebook_cell_run: TerminalIcon,
  question_submitted: SendIcon,
  attempt_submitted: SendIcon,
};

function iconFor(type: string): LucideIcon {
  return ICON_BY_TYPE[type] ?? ActivityIcon;
}

function severityFor(type: string): "info" | "warn" | "alert" {
  return SEVERITY[type] ?? "info";
}

function eventAttemptId(ev: AttemptEvent): string | null {
  const direct = ev.attempt_id;
  if (typeof direct === "string" && direct.length > 0) {
    return direct;
  }
  const fromPayload = (ev.payload as Record<string, unknown> | undefined)
    ?.attempt_id;
  if (typeof fromPayload === "string" && fromPayload.length > 0) {
    return fromPayload;
  }
  return null;
}

export function IntegrityEventTimeline({ events }: { events: AttemptEvent[] }) {
  const [active, setActive] = useState<Set<string>>(new Set());

  const counts = useMemo(() => {
    const out: Record<string, number> = {};
    for (const ev of events) {
      out[ev.event_type] = (out[ev.event_type] ?? 0) + 1;
    }
    return out;
  }, [events]);

  const filtered = useMemo(() => {
    if (active.size === 0) {
      return events;
    }
    return events.filter((ev) => active.has(ev.event_type));
  }, [events, active]);

  function toggle(type: string) {
    setActive((prev) => {
      const next = new Set(prev);
      if (next.has(type)) {
        next.delete(type);
      } else {
        next.add(type);
      }
      return next;
    });
  }

  if (events.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No integrity events recorded for this assignment.
      </p>
    );
  }

  const chips = Object.entries(counts).sort(([a], [b]) => a.localeCompare(b));

  return (
    <div className="space-y-3">
      <fieldset
        aria-label="Filter integrity events by type"
        className="flex flex-wrap items-center gap-2 border-0 p-0 text-xs"
      >
        {chips.map(([type, count]) => {
          const sev = severityFor(type);
          const Icon = iconFor(type);
          const pressed = active.has(type);
          return (
            <button
              aria-pressed={pressed}
              className={`inline-flex items-center gap-1.5 rounded border px-2 py-0.5 transition ${
                COLOR_BY_SEVERITY[sev]
              } ${pressed ? "ring-2 ring-foreground/30" : "opacity-90 hover:opacity-100"}`}
              key={type}
              onClick={() => toggle(type)}
              title={pressed ? "Click to clear filter" : "Click to filter"}
              type="button"
            >
              <Icon aria-hidden="true" className="h-3 w-3" />
              <span>{type.replaceAll("_", " ")}</span>
              <span>
                <span className="sr-only">{count} occurrences</span>
                <span aria-hidden="true">: {count}</span>
              </span>
            </button>
          );
        })}
        {active.size > 0 && (
          <button
            className="rounded border border-border/60 px-2 py-0.5 text-muted-foreground hover:text-foreground"
            onClick={() => setActive(new Set())}
            type="button"
          >
            Clear filters
          </button>
        )}
      </fieldset>

      <ol className="max-h-96 overflow-y-auto rounded border border-border/40 bg-background/30 text-xs">
        {filtered.map((ev) => {
          const sev = severityFor(ev.event_type);
          const Icon = iconFor(ev.event_type);
          const attemptId = eventAttemptId(ev);
          const label = ev.event_type.replaceAll("_", " ");
          let iconTone: string;
          if (sev === "alert") {
            iconTone = "text-destructive";
          } else if (sev === "warn") {
            iconTone = "text-warning";
          } else {
            iconTone = "text-primary";
          }
          return (
            <li
              className="flex items-start gap-3 border-border/30 border-b px-3 py-2 last:border-b-0"
              key={ev.id}
            >
              <span
                aria-hidden="true"
                className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${DOT_BY_SEVERITY[sev]}`}
              />
              <Icon
                aria-hidden="true"
                className={`mt-0.5 h-3.5 w-3.5 shrink-0 ${iconTone}`}
              />
              <div className="min-w-0 flex-1">
                {attemptId ? (
                  <Link
                    className="font-medium hover:text-primary hover:underline"
                    href={`#attempt-${attemptId}`}
                  >
                    {label}
                  </Link>
                ) : (
                  <p className="font-medium">{label}</p>
                )}
                {Object.keys(ev.payload || {}).length > 0 && (
                  <p className="truncate text-muted-foreground">
                    {JSON.stringify(ev.payload)}
                  </p>
                )}
              </div>
              <time
                className="shrink-0 text-muted-foreground"
                dateTime={ev.server_timestamp}
              >
                {new Date(ev.server_timestamp).toLocaleTimeString()}
              </time>
              {sev === "alert" && (
                <AlertTriangleIcon
                  aria-label="High severity"
                  className="mt-0.5 h-3.5 w-3.5 shrink-0 text-destructive"
                />
              )}
            </li>
          );
        })}
        {filtered.length === 0 && (
          <li className="px-3 py-3 text-center text-muted-foreground">
            No events match the active filter.
          </li>
        )}
      </ol>
    </div>
  );
}
