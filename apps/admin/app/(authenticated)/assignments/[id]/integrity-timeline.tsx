import type { AttemptEvent } from "@/lib/api";

const SEVERITY: Record<string, "info" | "warn" | "alert"> = {
  focus_lost: "warn",
  focus_gained: "info",
  visibility_hidden: "warn",
  visibility_visible: "info",
  fullscreen_entered: "info",
  fullscreen_exited: "alert",
  paste_blocked: "alert",
  copy_blocked: "warn",
  context_menu_blocked: "info",
  devtools_suspected: "alert",
  network_offline: "warn",
  network_online: "info",
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

export function IntegrityEventTimeline({ events }: { events: AttemptEvent[] }) {
  if (events.length === 0) {
    return (
      <p className="text-muted-foreground text-sm">
        No integrity events recorded for this assignment.
      </p>
    );
  }

  const counts: Record<string, number> = {};
  for (const ev of events) {
    counts[ev.event_type] = (counts[ev.event_type] ?? 0) + 1;
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap gap-2 text-xs">
        {Object.entries(counts).map(([type, count]) => {
          const sev = SEVERITY[type] ?? "info";
          return (
            <span
              className={`rounded border px-2 py-0.5 ${COLOR_BY_SEVERITY[sev]}`}
              key={type}
            >
              {type.replaceAll("_", " ")}: {count}
            </span>
          );
        })}
      </div>
      <ol className="max-h-96 overflow-y-auto rounded border border-border/40 bg-background/30 text-xs">
        {events.map((ev) => {
          const sev = SEVERITY[ev.event_type] ?? "info";
          return (
            <li
              className="flex items-start gap-3 border-border/30 border-b px-3 py-2 last:border-b-0"
              key={ev.id}
            >
              <span
                className={`mt-0.5 inline-block h-2 w-2 shrink-0 rounded-full ${DOT_BY_SEVERITY[sev]}`}
                aria-hidden="true"
              />
              <div className="flex-1 min-w-0">
                <p className="font-medium">{ev.event_type}</p>
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
            </li>
          );
        })}
      </ol>
    </div>
  );
}
