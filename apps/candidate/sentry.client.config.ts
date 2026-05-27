// Candidate app Sentry browser init. Routes errors to the candidate
// Sentry project (NEXT_PUBLIC_SENTRY_DSN_CANDIDATE). The actual
// Sentry.init body lives in @repo/observability/client so the config
// stays in lockstep with the admin app.

import { initializeSentry } from "@repo/observability/client";

initializeSentry("candidate");

export { onRouterTransitionStart } from "@repo/observability/client";
