/*
 * Admin app Sentry server-side init. Uses the per-app DSN
 * (NEXT_PUBLIC_SENTRY_DSN_ADMIN) with a fallback to the legacy
 * NEXT_PUBLIC_SENTRY_DSN. Spec §15/§16.
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
  includeLocalVariables: true,
  integrations: [
    Sentry.consoleLoggingIntegration({ levels: ["log", "error", "warn"] }),
  ],
});
