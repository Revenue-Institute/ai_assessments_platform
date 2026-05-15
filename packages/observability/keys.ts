import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

/**
 * Observability env keys.
 *
 * Spec §15 and §16 require three independent Sentry projects so that
 * admin, candidate, and api errors stay attributed to the right
 * surface area. The Next apps read the per-app public DSNs:
 *   - NEXT_PUBLIC_SENTRY_DSN_ADMIN
 *   - NEXT_PUBLIC_SENTRY_DSN_CANDIDATE
 * NEXT_PUBLIC_SENTRY_DSN is kept as a backward-compat fallback so
 * existing deploys keep reporting until they migrate.
 *
 * Source-map upload (next-config.ts) reads SENTRY_AUTH_TOKEN,
 * SENTRY_ORG, and the per-app SENTRY_PROJECT_ADMIN /
 * SENTRY_PROJECT_CANDIDATE. The legacy single SENTRY_PROJECT remains
 * a fallback for environments that have not migrated yet.
 */
export const keys = () =>
  createEnv({
    server: {
      BETTERSTACK_API_KEY: z.string().optional(),
      BETTERSTACK_URL: z.url().optional(),

      // Sentry source-map upload, per spec §16.
      SENTRY_AUTH_TOKEN: z.string().optional(),
      SENTRY_ORG: z.string().optional(),
      SENTRY_PROJECT: z.string().optional(),
      SENTRY_PROJECT_ADMIN: z.string().optional(),
      SENTRY_PROJECT_CANDIDATE: z.string().optional(),
    },
    client: {
      // Per-app DSNs (spec §16). Each Next app picks its own at init time.
      NEXT_PUBLIC_SENTRY_DSN: z.url().optional(),
      NEXT_PUBLIC_SENTRY_DSN_ADMIN: z.url().optional(),
      NEXT_PUBLIC_SENTRY_DSN_CANDIDATE: z.url().optional(),
    },
    runtimeEnv: {
      BETTERSTACK_API_KEY: process.env.BETTERSTACK_API_KEY,
      BETTERSTACK_URL: process.env.BETTERSTACK_URL,
      SENTRY_AUTH_TOKEN: process.env.SENTRY_AUTH_TOKEN,
      SENTRY_ORG: process.env.SENTRY_ORG,
      SENTRY_PROJECT: process.env.SENTRY_PROJECT,
      SENTRY_PROJECT_ADMIN: process.env.SENTRY_PROJECT_ADMIN,
      SENTRY_PROJECT_CANDIDATE: process.env.SENTRY_PROJECT_CANDIDATE,
      NEXT_PUBLIC_SENTRY_DSN: process.env.NEXT_PUBLIC_SENTRY_DSN,
      NEXT_PUBLIC_SENTRY_DSN_ADMIN: process.env.NEXT_PUBLIC_SENTRY_DSN_ADMIN,
      NEXT_PUBLIC_SENTRY_DSN_CANDIDATE:
        process.env.NEXT_PUBLIC_SENTRY_DSN_CANDIDATE,
    },
    emptyStringAsUndefined: true,
  });

/**
 * Resolve the correct DSN for the calling Next app.
 *
 * Resolution order:
 *   1. Explicit per-app DSN (NEXT_PUBLIC_SENTRY_DSN_ADMIN /
 *      NEXT_PUBLIC_SENTRY_DSN_CANDIDATE)
 *   2. Legacy shared NEXT_PUBLIC_SENTRY_DSN (back-compat)
 *
 * When `app` is omitted the resolver picks whichever per-app DSN is
 * present, then falls back to the shared DSN. This lets the shared
 * client.ts / server.ts wrappers stay app-agnostic; the Next app's
 * own env decides which project it ships to.
 */
export type ObservabilityApp = "admin" | "candidate";

export const resolveSentryDsn = (
  app?: ObservabilityApp
): string | undefined => {
  const env = keys();
  if (app === "admin") {
    return env.NEXT_PUBLIC_SENTRY_DSN_ADMIN ?? env.NEXT_PUBLIC_SENTRY_DSN;
  }
  if (app === "candidate") {
    return env.NEXT_PUBLIC_SENTRY_DSN_CANDIDATE ?? env.NEXT_PUBLIC_SENTRY_DSN;
  }
  return (
    env.NEXT_PUBLIC_SENTRY_DSN_ADMIN ??
    env.NEXT_PUBLIC_SENTRY_DSN_CANDIDATE ??
    env.NEXT_PUBLIC_SENTRY_DSN
  );
};

/**
 * Resolve the Sentry build-time project slug for source-map upload.
 * Mirrors resolveSentryDsn ordering: per-app first, then legacy
 * single SENTRY_PROJECT.
 */
export const resolveSentryProject = (
  app?: ObservabilityApp
): string | undefined => {
  const env = keys();
  if (app === "admin") {
    return env.SENTRY_PROJECT_ADMIN ?? env.SENTRY_PROJECT;
  }
  if (app === "candidate") {
    return env.SENTRY_PROJECT_CANDIDATE ?? env.SENTRY_PROJECT;
  }
  return (
    env.SENTRY_PROJECT_ADMIN ??
    env.SENTRY_PROJECT_CANDIDATE ??
    env.SENTRY_PROJECT
  );
};
