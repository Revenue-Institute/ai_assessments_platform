/**
 * Next.js config helpers for observability.
 * Sentry / withSentryConfig wrapping has been removed.
 */

export const withObservability = <T extends object>(sourceConfig: T): T =>
  sourceConfig;
