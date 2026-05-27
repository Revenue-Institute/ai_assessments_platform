// Admin app Sentry browser init. Routes errors to the admin Sentry
// project (NEXT_PUBLIC_SENTRY_DSN_ADMIN). The actual Sentry.init body
// lives in @repo/observability/client so the config stays in lockstep
// with the candidate app.

import { initializeSentry } from "@repo/observability/client";

initializeSentry("admin");

export { onRouterTransitionStart } from "@repo/observability/client";
