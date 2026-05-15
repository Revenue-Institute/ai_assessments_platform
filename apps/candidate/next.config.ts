import { withSentry } from "@repo/observability/next-config";
import type { NextConfig } from "next";

let nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  output: "standalone",
  typedRoutes: true,
};

// Source-map upload gate keyed on SENTRY_AUTH_TOKEN, not VERCEL: any
// build platform (Vercel, Cloud Run, GitHub Actions, local) ships
// source maps when the token is present. Spec §15/§16.
if (process.env.SENTRY_AUTH_TOKEN) {
  nextConfig = withSentry(nextConfig, "candidate");
}

export default nextConfig;
