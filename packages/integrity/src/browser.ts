import type { IntegrityEventType } from "@repo/schemas";

export type IntegrityEvent = {
  type: IntegrityEventType;
  payload?: Record<string, unknown>;
  client_timestamp?: string;
};

export type IntegrityMonitorOptions = {
  /** Called for every captured event. The caller is responsible for batching. */
  send: (event: IntegrityEvent) => void;
  /**
   * If a click target matches this selector, copy/cut/paste are allowed.
   * Defaults to the spec's `[data-allow-paste="true"]` (spec §10.2).
   */
  allowPasteSelector?: string;
};

const DEFAULT_ALLOW_PASTE_SELECTOR = '[data-allow-paste="true"]';

const BLOCKED_COMBOS: Array<{ key: string; meta?: boolean; ctrl?: boolean }> = [
  { key: "c", meta: true },
  { key: "v", meta: true },
  { key: "x", meta: true },
  { key: "c", ctrl: true },
  { key: "v", ctrl: true },
  { key: "x", ctrl: true },
  { key: "u", meta: true },
  { key: "s", meta: true },
  { key: "p", meta: true },
];

/** Spec §10.2 browser monitor. Returns a teardown function that removes
 * every listener it installed. Safe to call repeatedly; each call installs
 * a fresh, independent monitor. */
export function installIntegrityMonitor(
  options: IntegrityMonitorOptions
): () => void {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return () => undefined;
  }

  const allowPasteSelector =
    options.allowPasteSelector ?? DEFAULT_ALLOW_PASTE_SELECTOR;

  const stamp = (): string => new Date().toISOString();
  const send = (event: IntegrityEvent) =>
    options.send({
      ...event,
      client_timestamp: event.client_timestamp ?? stamp(),
    });

  const onVisibility = () => {
    send({
      type: document.hidden ? "visibility_hidden" : "visibility_visible",
    });
  };
  document.addEventListener("visibilitychange", onVisibility);

  const onBlur = () => send({ type: "focus_lost" });
  const onFocus = () => send({ type: "focus_gained" });
  window.addEventListener("blur", onBlur);
  window.addEventListener("focus", onFocus);

  const clipHandlers: Array<[keyof DocumentEventMap, EventListener]> = [];
  for (const evt of ["copy", "cut", "paste"] as const) {
    const handler = (e: Event) => {
      const target = e.target as HTMLElement | null;
      const allowed = !!target?.closest(allowPasteSelector);
      if (!allowed) {
        e.preventDefault();
      }
      send({
        type: `${evt}_attempted` as IntegrityEventType,
        payload: { allowed },
      });
    };
    document.addEventListener(evt, handler);
    clipHandlers.push([evt, handler]);
  }

  const onContextMenu = (e: MouseEvent) => {
    e.preventDefault();
    send({ type: "context_menu_opened" });
  };
  document.addEventListener("contextmenu", onContextMenu);

  const onKeyDown = (e: KeyboardEvent) => {
    const target = e.target as HTMLElement | null;
    const inAllowedZone = !!target?.closest(allowPasteSelector);
    const matched = BLOCKED_COMBOS.some(
      (combo) =>
        e.key.toLowerCase() === combo.key &&
        ((combo.meta && e.metaKey) || (combo.ctrl && e.ctrlKey))
    );
    if (matched && !inAllowedZone) {
      e.preventDefault();
      send({
        type: "keyboard_shortcut_blocked",
        payload: { key: e.key, meta: e.metaKey, ctrl: e.ctrlKey },
      });
    }
  };
  document.addEventListener("keydown", onKeyDown);

  const onFullscreen = () => {
    send({
      type: document.fullscreenElement
        ? "fullscreen_entered"
        : "fullscreen_exited",
    });
  };
  document.addEventListener("fullscreenchange", onFullscreen);

  let lastWidth = window.innerWidth;
  const onResize = () => {
    if (window.innerWidth < lastWidth * 0.7) {
      send({
        type: "window_resized",
        payload: { from: lastWidth, to: window.innerWidth },
      });
    }
    lastWidth = window.innerWidth;
  };
  window.addEventListener("resize", onResize);

  const onOnline = () => send({ type: "network_online" });
  const onOffline = () => send({ type: "network_offline" });
  window.addEventListener("online", onOnline);
  window.addEventListener("offline", onOffline);

  // DevTools heuristic: outerWidth - innerWidth > 160 px is a weak signal
  // (always false in normal browsing). Best-effort, no false alarm in dev.
  const DEV_TOOLS_THRESHOLD = 160;
  let devtoolsFlagged = false;
  const devtoolsTimer = window.setInterval(() => {
    const widthGap = window.outerWidth - window.innerWidth;
    const heightGap = window.outerHeight - window.innerHeight;
    const open = widthGap > DEV_TOOLS_THRESHOLD || heightGap > DEV_TOOLS_THRESHOLD;
    if (open && !devtoolsFlagged) {
      devtoolsFlagged = true;
      send({ type: "devtools_opened" });
    } else if (!open) {
      devtoolsFlagged = false;
    }
  }, 2000);

  return () => {
    document.removeEventListener("visibilitychange", onVisibility);
    window.removeEventListener("blur", onBlur);
    window.removeEventListener("focus", onFocus);
    for (const [evt, handler] of clipHandlers) {
      document.removeEventListener(evt, handler);
    }
    document.removeEventListener("contextmenu", onContextMenu);
    document.removeEventListener("keydown", onKeyDown);
    document.removeEventListener("fullscreenchange", onFullscreen);
    window.removeEventListener("resize", onResize);
    window.removeEventListener("online", onOnline);
    window.removeEventListener("offline", onOffline);
    window.clearInterval(devtoolsTimer);
  };
}
