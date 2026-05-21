import { withSentry } from "@repo/observability/next-config";
import type { NextConfig } from "next";

// In single-host prod, admin (assessments.revenueinstitute.com) rewrites
// /a/* to the candidate origin. The rewrite returns candidate HTML, but
// chunk URLs default to relative paths (/_next/static/...) which the
// browser then requests from admin's host and admin 404s. Pinning
// assetPrefix to the candidate's own origin makes those URLs absolute
// so chunks load directly from the candidate deployment. Leave the env
// var unset in dev (same-origin, no prefix needed).
const assetOrigin = process.env.NEXT_PUBLIC_CANDIDATE_ASSET_ORIGIN?.replace(
  /\/+$/,
  ""
);

let nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  typedRoutes: true,
  ...(assetOrigin ? { assetPrefix: assetOrigin } : {}),
};

// Source-map upload gate keyed on SENTRY_AUTH_TOKEN, not VERCEL: any
// build platform (Vercel, Cloud Run, GitHub Actions, local) ships
// source maps when the token is present. Spec §15/§16.
if (process.env.SENTRY_AUTH_TOKEN) {
  nextConfig = withSentry(nextConfig, "candidate");
}

export default nextConfig;
