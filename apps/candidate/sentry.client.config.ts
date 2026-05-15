/*
 * Candidate app Sentry browser init. Per-app DSN
 * (NEXT_PUBLIC_SENTRY_DSN_CANDIDATE) with a fallback to the legacy
 * NEXT_PUBLIC_SENTRY_DSN. Spec §15/§16.
 */

// biome-ignore lint/performance/noNamespaceImport: Sentry SDK convention
import * as Sentry from "@sentry/nextjs";

Sentry.init({
  dsn:
    process.env.NEXT_PUBLIC_SENTRY_DSN_CANDIDATE ??
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
