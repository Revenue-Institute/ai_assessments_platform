// Admin app Sentry server-side init. See @repo/observability/server
// for the shared Sentry.init body.

import { initializeSentry } from "@repo/observability/server";

initializeSentry("admin");
