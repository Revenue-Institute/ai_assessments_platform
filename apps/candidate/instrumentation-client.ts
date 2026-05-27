import { initializeSentry } from "@repo/observability/client";

initializeSentry("candidate");

export { onRouterTransitionStart } from "@repo/observability/client";
