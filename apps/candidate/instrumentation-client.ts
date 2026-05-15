import { initializeSentry } from "@repo/observability/client";

initializeSentry();

export { onRouterTransitionStart } from "@repo/observability/client";
