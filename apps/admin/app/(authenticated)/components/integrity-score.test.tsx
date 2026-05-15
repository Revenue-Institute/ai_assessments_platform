import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { IntegrityScore } from "./integrity-score";

afterEach(() => {
  cleanup();
});

describe("IntegrityScore", () => {
  it("renders the primary (green) tone for scores >= 85", () => {
    const { container } = render(<IntegrityScore score={90} />);
    const span = container.querySelector("span");
    expect(span).not.toBeNull();
    expect(span?.className).toContain("text-primary");
    expect(span?.className).not.toContain("text-warning");
    expect(span?.className).not.toContain("text-destructive");
  });

  it("renders the warning (yellow) tone for scores 60-84", () => {
    for (const score of [60, 70, 84]) {
      const { container, unmount } = render(<IntegrityScore score={score} />);
      const span = container.querySelector("span");
      expect(span?.className).toContain("text-warning");
      expect(span?.className).not.toContain("text-primary");
      expect(span?.className).not.toContain("text-destructive");
      unmount();
    }
  });

  it("renders the destructive (red) tone for scores < 60", () => {
    const { container } = render(<IntegrityScore score={45} />);
    const span = container.querySelector("span");
    expect(span?.className).toContain("text-destructive");
    expect(span?.className).not.toContain("text-primary");
    expect(span?.className).not.toContain("text-warning");
  });

  it("returns nothing for null/undefined when fallback is not requested", () => {
    const { container: cNull } = render(<IntegrityScore score={null} />);
    expect(cNull.firstChild).toBeNull();
    const { container: cUndef } = render(<IntegrityScore score={undefined} />);
    expect(cUndef.firstChild).toBeNull();
  });

  it("renders an ASCII hyphen fallback when fallback is enabled", () => {
    const { container } = render(<IntegrityScore fallback score={null} />);
    expect(container.textContent).toBe("-");
  });

  it("exposes the numeric score on the accessible name and title", () => {
    const { container } = render(<IntegrityScore score={88} />);
    const span = container.querySelector("span");
    expect(span?.getAttribute("title")).toBe("Integrity score 88 of 100");
    // sr-only span carries the numeric score for screen readers.
    expect(container.textContent).toContain("88");
  });

  it("rounds the displayed score", () => {
    const { container } = render(<IntegrityScore score={87.6} />);
    expect(container.textContent).toContain("88");
  });
});
