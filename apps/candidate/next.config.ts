import { withSentry } from "@repo/observability/next-config";
import type { NextConfig } from "next";

// Single-host prod (single VM behind nginx): admin owns `/`, candidate
// owns `/a/*`. Without an asset prefix the served HTML refers to
// `/_next/static/...` which nginx routes to admin (the default `/`
// location), and admin 404s those chunks. Setting assetPrefix to "/a"
// makes the URLs `/a/_next/static/...`; the matching nginx regex
// location strips `/a` and forwards to the candidate container, which
// serves chunks at `/_next/...` as usual. Leave the env var unset in
// dev (same-origin localhost, no prefix needed).
const assetPrefix = process.env.NEXT_PUBLIC_CANDIDATE_ASSET_PREFIX?.replace(
  /\/+$/,
  ""
);

let nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  typedRoutes: true,
  // Workspace packages that export TypeScript source (`main: src/index.ts`
  // with `.js`-suffixed relative re-exports). Without this, turbopack's
  // RSC bundler fails to resolve `./module.js` -> `./module.ts` and the
  // entire barrel re-exports as "module has no exports at all". Type-only
  // imports tree-shake the chain away, which is why earlier admin builds
  // worked; the new runtime imports of `parseMcqConfig` etc. force the
  // full module load.
  transpilePackages: ["@repo/schemas", "@repo/design-system"],
  ...(assetPrefix ? { assetPrefix } : {}),
};

// Source-map upload gate keyed on SENTRY_AUTH_TOKEN, not VERCEL: any
// build platform (Vercel, Cloud Run, GitHub Actions, local) ships
// source maps when the token is present. Spec §15/§16.
if (process.env.SENTRY_AUTH_TOKEN) {
  nextConfig = withSentry(nextConfig, "candidate");
}

export default nextConfig;
