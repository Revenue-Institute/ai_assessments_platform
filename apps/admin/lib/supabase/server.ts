import { createServerClient as createSSRServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";
import { env } from "@/env";

export async function createSupabaseServerClient() {
  const cookieStore = await cookies();
  return createSSRServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll();
        },
        setAll(cookiesToSet) {
          try {
            for (const { name, value, options } of cookiesToSet) {
              cookieStore.set(name, value, options);
            }
          } catch {
            // Server components cannot set cookies; this is expected when
            // called from a server component instead of a route handler or
            // middleware. Session refresh happens in middleware.
          }
        },
      },
    }
  );
}

import { createServerClient as createServiceClient } from "@repo/db";

export function createSupabaseServiceClient() {
  return createServiceClient({
    url: env.SUPABASE_URL,
    serviceRoleKey: env.SUPABASE_SERVICE_ROLE_KEY,
  });
}
