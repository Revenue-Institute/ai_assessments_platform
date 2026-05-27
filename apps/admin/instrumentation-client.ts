import { initializeSentry } from "@repo/observability/client";

initializeSentry("admin");

export { onRouterTransitionStart } from "@repo/observability/client";
