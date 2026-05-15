import { withLogtail } from "@logtail/next";
import { withSentryConfig } from "@sentry/nextjs";
import { keys, type ObservabilityApp, resolveSentryProject } from "./keys";

/**
 * Build the Sentry build-plugin config for a given Next app.
 *
 * Per spec §15 and §16 the admin and candidate apps each upload
 * source maps to their own Sentry project. The plugin reads
 * SENTRY_AUTH_TOKEN, SENTRY_ORG, and SENTRY_PROJECT_{ADMIN,CANDIDATE}
 * at build time. Older deploys that still set the shared
 * SENTRY_PROJECT keep working via the fallback in resolveSentryProject().
 */
export const buildSentryConfig = (
  app?: ObservabilityApp
): Parameters<typeof withSentryConfig>[1] => ({
  org: keys().SENTRY_ORG,
  project: resolveSentryProject(app),

  // The Sentry plugin picks SENTRY_AUTH_TOKEN up automatically from
  // process.env, but listing it here keeps the contract explicit for
  // anyone reading this file.
  authToken: keys().SENTRY_AUTH_TOKEN,

  // Only print logs for uploading source maps in CI
  silent: !process.env.CI,

  /*
   * For all available options, see:
   * https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/
   */

  // Upload a larger set of source maps for prettier stack traces (increases build time)
  widenClientFileUpload: true,

  /*
   * Route browser requests to Sentry through a Next.js rewrite to circumvent ad-blockers.
   * This can increase your server load as well as your hosting bill.
   * Note: Check that the configured route will not match with your Next.js middleware, otherwise reporting of client-
   * side errors will fail.
   */
  tunnelRoute: "/monitoring",

  webpack: {
    // Automatically tree-shake Sentry logger statements to reduce bundle size
    treeshake: {
      removeDebugLogging: true,
    },

    /*
     * Enables automatic instrumentation of Vercel Cron Monitors. (Does not yet work with App Router route handlers.)
     * See the following for more information:
     * https://docs.sentry.io/product/crons/
     * https://vercel.com/docs/cron-jobs
     */
    automaticVercelMonitors: true,
  },
});

// Legacy export kept for back-compat with any caller importing the
// raw config object. Equivalent to buildSentryConfig() with no app
// hint, i.e. it falls through to SENTRY_PROJECT.
export const sentryConfig = buildSentryConfig();

export const withSentry = (
  sourceConfig: object,
  app?: ObservabilityApp
): object => {
  const configWithTranspile = {
    ...sourceConfig,
    transpilePackages: ["@sentry/nextjs"],
  };

  return withSentryConfig(configWithTranspile, buildSentryConfig(app));
};

export const withLogging = (config: object): object => {
  // @logtail/next prints "Envvars not detected" / "Sending logs to console"
  // every time it loads when LOGTAIL_SOURCE_TOKEN is unset; we don't ship
  // Logtail in v1 (Sentry + Axiom per spec §15), so skip the wrapper
  // entirely when the token isn't configured.
  if (!process.env.LOGTAIL_SOURCE_TOKEN) {
    return config;
  }
  return withLogtail(config);
};
