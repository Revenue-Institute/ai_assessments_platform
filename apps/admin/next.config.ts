import { config, withAnalyzer } from "@repo/next-config";
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
  ""
);

let nextConfig: NextConfig = {
  ...config,
  output: "standalone",
  // Workspace packages that export TypeScript source (`main: src/index.ts`
  // with `.js`-suffixed relative re-exports). Mirrors the candidate
  // app's next.config.ts; required so the admin preview renderer can
  // pull parseXxxConfig at runtime via @repo/schemas. The shared
  // question-renderer also lives under @repo/design-system.
  transpilePackages: ["@repo/schemas", "@repo/design-system"],
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
};

if (process.env.ANALYZE === "true") {
  nextConfig = withAnalyzer(nextConfig);
}

export default nextConfig;
