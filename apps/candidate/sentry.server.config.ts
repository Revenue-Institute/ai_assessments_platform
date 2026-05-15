/*
 * Candidate app Sentry server-side init. Per-app DSN with legacy
 * fallback (spec §15/§16).
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
  includeLocalVariables: true,
  integrations: [
    Sentry.consoleLoggingIntegration({ levels: ["log", "error", "warn"] }),
  ],
});
