import { createEnv } from "@t3-oss/env-nextjs";
import { z } from "zod";

export const env = createEnv({
  server: {
    INTERNAL_API_URL: z.string().url().default("http://localhost:8000"),
    JWT_SIGNING_SECRET: z.string().min(1).optional(),
  },
  client: {
    NEXT_PUBLIC_API_URL: z.string().url().default("http://localhost:8000"),
    NEXT_PUBLIC_CANDIDATE_URL: z
      .string()
      .url()
      .default("http://localhost:3001"),
  },
  runtimeEnv: {
    INTERNAL_API_URL: process.env.INTERNAL_API_URL,
    JWT_SIGNING_SECRET: process.env.JWT_SIGNING_SECRET,
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
    NEXT_PUBLIC_CANDIDATE_URL: process.env.NEXT_PUBLIC_CANDIDATE_URL,
  },
});
