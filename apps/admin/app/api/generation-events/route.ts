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
  // Supabase Bearer token here. Mirrors apps/admin/app/api/scoring-events
  // for the question-generation progress feed (spec §6.1 stage 2 fan-out).
  const supabase = await createSupabaseServerClient();
  const {
    data: { session },
  } = await supabase.auth.getSession();
  if (!session?.access_token) {
    return new Response("Not signed in.", { status: 401 });
  }

  const runId = request.nextUrl.searchParams.get("run_id");
  if (!runId) {
    return new Response("Missing run_id.", { status: 400 });
  }

  const upstream = new URL(
    `${env.INTERNAL_API_URL.replace(TRAILING_SLASH_RE, "")}/api/generator/runs/${encodeURIComponent(runId)}/events`
  );

  const upstreamRes = await fetch(upstream, {
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      Accept: "text/event-stream",
    },
    // Forward client aborts so the upstream releases its publisher slot.
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
