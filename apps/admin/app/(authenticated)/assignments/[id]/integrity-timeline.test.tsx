import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
} from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AttemptEvent } from "@/lib/api";
import { IntegrityEventTimeline } from "./integrity-timeline";

afterEach(() => {
  cleanup();
});

// next/link in tests just renders an anchor.
vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...rest
  }: {
    children: React.ReactNode;
    href: string;
  }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function makeEvent(
  overrides: Partial<AttemptEvent> & { event_type: string }
): AttemptEvent {
  return {
    attempt_id: null,
    client_timestamp: "2026-04-01T00:00:00.000Z",
    id: `${overrides.event_type}-id`,
    payload: {},
    server_timestamp: "2026-04-01T00:00:01.000Z",
    user_agent: null,
    ...overrides,
  };
}

describe("IntegrityEventTimeline", () => {
  it("uses canonical integrity event-type names in its severity map", () => {
    // Render a sample of canonical event types and confirm each shows up as a
    // filter chip with a button (which proves it lives in the severity map).
    const sample = [
      "paste_attempted",
      "copy_attempted",
      "cut_attempted",
      "fullscreen_exited",
      "devtools_opened",
      "focus_lost",
      "visibility_hidden",
    ];
    const events = sample.map((t) => makeEvent({ event_type: t }));
    render(<IntegrityEventTimeline events={events} />);

    for (const t of sample) {
      const label = t.replaceAll("_", " ");
      const button = screen
        .getAllByRole("button")
        .find((b) => within(b).queryByText(label));
      expect(button, `expected chip for ${t}`).toBeDefined();
    }
  });

  it("toggles aria-pressed when a filter chip is clicked", () => {
    const events = [
      makeEvent({ event_type: "paste_attempted" }),
      makeEvent({ event_type: "focus_lost", id: "focus-1" }),
    ];
    render(<IntegrityEventTimeline events={events} />);

    const buttons = screen.getAllByRole("button");
    const pasteChip = buttons.find((b) =>
      within(b).queryByText("paste attempted")
    );
    expect(pasteChip).toBeDefined();
    if (!pasteChip) {
      throw new Error("paste chip not rendered");
    }
    expect(pasteChip.getAttribute("aria-pressed")).toBe("false");

    fireEvent.click(pasteChip);
    expect(pasteChip.getAttribute("aria-pressed")).toBe("true");

    fireEvent.click(pasteChip);
    expect(pasteChip.getAttribute("aria-pressed")).toBe("false");
  });

  it("renders an anchor link when the event has an attempt_id payload", () => {
    const events = [
      makeEvent({
        attempt_id: "att-99",
        event_type: "code_executed",
        id: "ev-1",
      }),
      makeEvent({
        event_type: "focus_lost",
        id: "ev-2",
        payload: { attempt_id: "att-77" },
      }),
      makeEvent({ event_type: "attempt_submitted", id: "ev-3" }),
    ];
    render(<IntegrityEventTimeline events={events} />);

    const directLink = screen
      .getAllByRole("link")
      .find((a) => a.getAttribute("href") === "#attempt-att-99");
    expect(directLink).toBeDefined();

    const payloadLink = screen
      .getAllByRole("link")
      .find((a) => a.getAttribute("href") === "#attempt-att-77");
    expect(payloadLink).toBeDefined();

    // Plain p element for events without an attempt id (chip is the
    // button-with-aria-pressed; the list item uses a paragraph).
    const matches = screen.getAllByText("attempt submitted");
    const paragraph = matches.find((el) => el.tagName === "P");
    expect(paragraph).toBeDefined();
  });

  it("renders the empty-state when given no events", () => {
    render(<IntegrityEventTimeline events={[]} />);
    expect(
      screen.getByText("No integrity events recorded for this assignment.")
    ).toBeTruthy();
  });
});
