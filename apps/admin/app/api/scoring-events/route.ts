import type { NextRequest } from "next/server";
import { env } from "@/env";
import { createSupabaseServerClient } from "@/lib/supabase/server";

// Node runtime: createSupabaseServerClient reads cookies via next/headers.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

const TRAILING_SLASH_RE = /\/$/;

export async function GET(request: NextRequest) {
  // Browser EventSource cannot send Authorization headers, so the admin
  // app proxies the FastAPI SSE stream and attaches the signed-in admin's
  // Supabase Bearer token here. Production deploys terminate this on the
  // same host, so there's no extra hop crossing the public internet.
  const supabase = await createSupabaseServerClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return new Response("Not signed in.", { status: 401 });
  }

  const assignmentId = request.nextUrl.searchParams.get("assignment_id");
  const upstream = new URL(
    `${env.INTERNAL_API_URL.replace(TRAILING_SLASH_RE, "")}/api/scoring-events`
  );
  if (assignmentId) {
    upstream.searchParams.set("assignment_id", assignmentId);
  }

  const upstreamRes = await fetch(upstream, {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      Accept: "text/event-stream",
    },
    // Forward client aborts so the upstream releases its Redis pubsub.
    signal: request.signal,
    cache: "no-store",
  });

  if (!(upstreamRes.ok && upstreamRes.body)) {
    return new Response(`Upstream SSE error: ${upstreamRes.status}`, {
      status: upstreamRes.status || 502,
    });
  }

  return new Response(upstreamRes.body, {
    status: 200,
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
      "X-Accel-Buffering": "no",
    },
  });
}
