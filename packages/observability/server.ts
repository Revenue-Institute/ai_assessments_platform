/*
 * Sentry server-side init. Shared by both Next apps' sentry.server.config.ts
 * and instrumentation. DSN resolution mirrors client.ts: per-app DSN first,
 * legacy NEXT_PUBLIC_SENTRY_DSN as fallback (spec §16).
 */

// biome-ignore lint/performance/noNamespaceImport: Sentry SDK convention
import * as Sentry from "@sentry/nextjs";
import { resolveSentryDsn } from "./keys";

export const initializeSentry = (): ReturnType<typeof Sentry.init> =>
  Sentry.init({
    dsn: resolveSentryDsn(),

    environment: process.env.APP_ENV ?? process.env.NODE_ENV ?? "production",

    // PII policy (spec §18). Mirrors the FastAPI service: no raw IPs,
    // request bodies, or candidate answers are forwarded to Sentry.
    sendDefaultPii: false,

    // Enable logging
    enableLogs: true,

    // Adjust this value in production, or use tracesSampler for greater control
    tracesSampleRate: 1,

    // Setting this option to true will print useful information to the console while you're setting up Sentry.
    debug: false,

    // Capture local variables in stack traces for better debugging
    includeLocalVariables: true,

    // Integrations for console logging
    integrations: [
      // Send console.log, console.error, and console.warn calls as logs to Sentry
      Sentry.consoleLoggingIntegration({ levels: ["log", "error", "warn"] }),
    ],
  });
