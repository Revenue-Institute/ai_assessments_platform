import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

/**
 * Observability env keys (Axiom/Better Stack uptime).
 * Sentry has been removed from this package.
 */
export const keys = () =>
  createEnv({
    server: {
      BETTERSTACK_API_KEY: z.string().optional(),
      BETTERSTACK_URL: z.url().optional(),
    },
    client: {},
    runtimeEnv: {
      BETTERSTACK_API_KEY: process.env.BETTERSTACK_API_KEY,
      BETTERSTACK_URL: process.env.BETTERSTACK_URL,
    },
    emptyStringAsUndefined: true,
  });
