/*
 * Sentry browser-side init. Shared by both Next apps via
 * `sentry.client.config.ts` / `instrumentation-client.ts`. The DSN is
 * resolved per spec §16: admin and candidate use independent Sentry
 * projects so errors stay attributed to the right surface.
 */

// biome-ignore lint/performance/noNamespaceImport: Sentry SDK convention
import * as Sentry from "@sentry/nextjs";
import { type ObservabilityApp, resolveSentryDsn } from "./keys";

export const initializeSentry = (
  app?: ObservabilityApp
): ReturnType<typeof Sentry.init> =>
  Sentry.init({
    // Per-app DSN with legacy NEXT_PUBLIC_SENTRY_DSN fallback. Callers
    // pass their app slug ("admin" / "candidate") so a misconfigured
    // env that defines both DSNs still routes to the correct project.
    dsn: resolveSentryDsn(app),

    environment: process.env.APP_ENV ?? process.env.NODE_ENV ?? "production",

    // PII policy (spec §18). We hash IPs server-side and strip raw
    // bodies; tell Sentry not to attach default PII either.
    sendDefaultPii: false,

    // Enable logging
    enableLogs: true,

    // Adjust this value in production, or use tracesSampler for greater control
    tracesSampleRate: 1,

    // Setting this option to true will print useful information to the console while you're setting up Sentry.
    debug: false,

    replaysOnErrorSampleRate: 1,

    /*
     * This sets the sample rate to be 10%. You may want this to be 100% while
     * in development and sample at a lower rate in production
     */
    replaysSessionSampleRate: 0.1,

    // You can remove this option if you're not planning to use the Sentry Session Replay feature:
    integrations: [
      Sentry.replayIntegration({
        // Additional Replay configuration goes in here, for example:
        maskAllText: true,
        blockAllMedia: true,
      }),
      // Send console.log, console.error, and console.warn calls as logs to Sentry
      Sentry.consoleLoggingIntegration({ levels: ["log", "error", "warn"] }),
    ],
  });

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
