/*
 * Admin app Sentry browser init. The shared @repo/observability/client
 * resolver also reads NEXT_PUBLIC_SENTRY_DSN_ADMIN with a fallback to
 * the legacy shared DSN; this file calls it directly so any tooling
 * looking for the canonical sentry.client.config.ts entry point keeps
 * working (Next 14 layout). instrumentation-client.ts (Next 15) wraps
 * the same init.
 */

// biome-ignore lint/performance/noNamespaceImport: Sentry SDK convention
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn:
    process.env.NEXT_PUBLIC_SENTRY_DSN_ADMIN ??
    process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.APP_ENV ?? "production",
  sendDefaultPii: false,
  enableLogs: true,
  tracesSampleRate: 1,
  debug: false,
  replaysOnErrorSampleRate: 1,
  replaysSessionSampleRate: 0.1,
  integrations: [
    Sentry.replayIntegration({
      maskAllText: true,
      blockAllMedia: true,
    }),
    Sentry.consoleLoggingIntegration({ levels: ["log", "error", "warn"] }),
  ],
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
