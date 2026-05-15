// @vitest-environment jsdom

import { afterEach, describe, expect, it, vi } from "vitest";
import {
  emitIntegrityEvent,
  type IntegrityEvent,
  installIntegrityMonitor,
} from "../src/browser";

const teardowns: Array<() => void> = [];

const ISO_TIMESTAMP_PREFIX_RE = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}/;

afterEach(() => {
  while (teardowns.length > 0) {
    const fn = teardowns.pop();
    fn?.();
  }
});

function mount(send: (event: IntegrityEvent) => void): void {
  const stop = installIntegrityMonitor({ send });
  teardowns.push(stop);
}

describe("emitIntegrityEvent", () => {
  it("queues an event on the active monitor's sink", () => {
    const send = vi.fn();
    mount(send);

    emitIntegrityEvent("code_executed", { language: "python" });

    expect(send).toHaveBeenCalledTimes(1);
    const event = send.mock.calls[0]?.[0] as IntegrityEvent;
    expect(event.type).toBe("code_executed");
    expect(event.payload).toEqual({ language: "python" });
    expect(event.client_timestamp).toMatch(ISO_TIMESTAMP_PREFIX_RE);
  });

  it("is a no-op when no monitor is mounted", () => {
    expect(() =>
      emitIntegrityEvent("n8n_workflow_saved", { node_count: 4 })
    ).not.toThrow();
  });

  it("is a no-op after the most recent monitor is torn down", () => {
    const send = vi.fn();
    const stop = installIntegrityMonitor({ send });

    stop();
    emitIntegrityEvent("notebook_cell_run");

    expect(send).not.toHaveBeenCalled();
  });
});

describe("installIntegrityMonitor", () => {
  it("routes emitIntegrityEvent to the most recently mounted monitor", () => {
    const first = vi.fn();
    const second = vi.fn();
    mount(first);
    mount(second);

    emitIntegrityEvent("interactive_state_saved");

    expect(first).not.toHaveBeenCalled();
    expect(second).toHaveBeenCalledTimes(1);
    const event = second.mock.calls[0]?.[0] as IntegrityEvent;
    expect(event.type).toBe("interactive_state_saved");
  });

  it("returns a teardown that detaches the listeners it installed", () => {
    const send = vi.fn();
    const stop = installIntegrityMonitor({ send });

    stop();

    // Visibility change should no longer be reported.
    document.dispatchEvent(new Event("visibilitychange"));
    expect(send).not.toHaveBeenCalled();
  });

  it("captures visibilitychange while mounted", () => {
    const send = vi.fn();
    mount(send);

    document.dispatchEvent(new Event("visibilitychange"));

    expect(send).toHaveBeenCalled();
    const types = send.mock.calls.map(
      (call) => (call[0] as IntegrityEvent).type
    );
    expect(types).toContain("visibility_visible");
  });
});
