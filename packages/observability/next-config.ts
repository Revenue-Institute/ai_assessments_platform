/**
 * Next.js config helpers for observability.
 * Error-tracking SaaS wrapping has been removed.
 */

export const withObservability = <T extends object>(sourceConfig: T): T =>
  sourceConfig;
