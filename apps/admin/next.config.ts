import { config, withAnalyzer } from "@repo/next-config";
import { withLogging, withSentry } from "@repo/observability/next-config";
import type { NextConfig } from "next";

// In production we serve the admin and the candidate apps from a single
// host (assessments.revenueinstitute.com). The admin owns the root and
// rewrites /a/* to the candidate deployment. Local dev keeps two ports
// so each app can hot-reload independently; the rewrite is opt-in via
// NEXT_PUBLIC_CANDIDATE_URL.
//
// Set NEXT_PUBLIC_CANDIDATE_URL to https://candidate.<env>.example or
// the candidate Vercel deployment URL. Leave unset for vanilla local
// dev (the magic-link emails point at the candidate's own host).
const candidateOrigin = process.env.NEXT_PUBLIC_CANDIDATE_URL?.replace(
  /\/+$/,
  "",
);

let nextConfig: NextConfig = withLogging({
  ...config,
  output: "standalone",
  // biome-ignore lint/suspicious/useAwait: rewrites is async
  async rewrites() {
    const baseRewrites = (await config.rewrites?.()) ?? [];
    const baseList = Array.isArray(baseRewrites)
      ? baseRewrites
      : [
          ...(baseRewrites.beforeFiles ?? []),
          ...(baseRewrites.afterFiles ?? []),
          ...(baseRewrites.fallback ?? []),
        ];
    if (!candidateOrigin) {
      return baseList;
    }
    return [
      ...baseList,
      {
        source: "/a/:path*",
        destination: `${candidateOrigin}/a/:path*`,
      },
    ];
  },
});

if (process.env.VERCEL) {
  nextConfig = withSentry(nextConfig);
}

if (process.env.ANALYZE === "true") {
  nextConfig = withAnalyzer(nextConfig);
}

export default nextConfig;
