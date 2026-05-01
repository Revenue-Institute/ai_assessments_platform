import { createServerClient } from "@supabase/ssr";
import { type NextRequest, NextResponse } from "next/server";

const PUBLIC_PATHS = ["/sign-in", "/sign-in/callback"];

export async function updateSession(request: NextRequest) {
  // Forward the pathname to the (authenticated) layout so role-based
  // redirects don't have to re-parse the URL via next/headers gymnastics.
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set("x-pathname", request.nextUrl.pathname);

  let response = NextResponse.next({ request: { headers: requestHeaders } });

  const supabase = createServerClient(
    process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? "",
    {
      cookies: {
        getAll() {
          return request.cookies.getAll();
        },
        setAll(cookiesToSet: { name: string; value: string; options: any }[]) {
          for (const { name, value } of cookiesToSet) {
            request.cookies.set(name, value);
          }
          response = NextResponse.next({
            request: { headers: requestHeaders },
          });
          for (const { name, value, options } of cookiesToSet) {
            response.cookies.set(name, value, options);
          }
        },
      },
    }
  );

  // Only call getUser() when an auth cookie is actually present. Without
  // this guard, every request from a signed-out browser triggers an
  // AuthApiError(refresh_token_not_found) that the Supabase SDK logs
  // directly to stderr before returning user=null - try/catch can't
  // suppress it because the log is a side effect of the SDK's internal
  // refresh call. Looking up the cookie ourselves and short-circuiting
  // is the only clean way to keep the dev console quiet.
  const hasSupabaseCookie = request.cookies
    .getAll()
    .some((c) => c.name.startsWith("sb-") && c.name.endsWith("-auth-token"));
  let user: Awaited<ReturnType<typeof supabase.auth.getUser>>["data"]["user"] =
    null;
  if (hasSupabaseCookie) {
    try {
      const result = await supabase.auth.getUser();
      user = result.data.user;
    } catch {
      // Stale or malformed cookie; the !user redirect handles it.
    }
  }

  const path = request.nextUrl.pathname;
  const isPublic = PUBLIC_PATHS.some((p) => path === p || path.startsWith(`${p}/`));

  if (!user && !isPublic) {
    const url = request.nextUrl.clone();
    url.pathname = "/sign-in";
    url.searchParams.set("next", path);
    return NextResponse.redirect(url);
  }

  if (user && path === "/sign-in") {
    const url = request.nextUrl.clone();
    url.pathname = "/";
    url.searchParams.delete("next");
    return NextResponse.redirect(url);
  }

  return response;
}
