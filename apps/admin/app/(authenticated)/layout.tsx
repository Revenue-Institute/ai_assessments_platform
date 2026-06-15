import { SidebarProvider } from "@repo/design-system/components/ui/sidebar";
import type { User } from "@supabase/supabase-js";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { NavigationProgress } from "@/components/navigation-progress";
import { ApiError, fetchAdminMe } from "@/lib/api";
import { canAccessPath } from "@/lib/role-policy";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { GlobalSidebar } from "./components/sidebar";

// Every page under (authenticated) reads cookies + headers for auth and
// role gating; nothing here is statically renderable. Marking the layout
// dynamic prevents Next from attempting prerender on any descendant.
export const dynamic = "force-dynamic";

export default async function AuthenticatedLayout({
  children,
}: {
  children: ReactNode;
}) {
  const supabase = await createSupabaseServerClient();
  // Defensive try/catch: Supabase logs AuthApiError to stderr on stale
  // refresh-token cookies even though the call returns user=null. Trap
  // it here so the dev console stays clean; the !user redirect handles
  // the not-signed-in path either way.
  let user: User | null = null;
  try {
    const result = await supabase.auth.getUser();
    user = result.data.user;
  } catch {
    // Fall through to the redirect below.
  }

  if (!user) {
    redirect("/sign-in");
  }

  // Resolve the application-level role (admin/reviewer/viewer). The
  // FastAPI side is the source of truth: it joins the Supabase JWT to
  // the public.users row, which carries the role check constraint.
  let me: Awaited<ReturnType<typeof fetchAdminMe>>;
  try {
    me = await fetchAdminMe();
  } catch (err) {
    if (err instanceof ApiError && (err.status === 401 || err.status === 403)) {
      redirect("/sign-in?reason=unprovisioned");
    }
    throw err;
  }

  // Path-based role gate: redirect away from routes the role can't access.
  // Lets viewers / reviewers click through the sidebar without 403s.
  const requestHeaders = await headers();
  const path = requestHeaders.get("x-pathname") ?? "/";
  if (!canAccessPath(me.role, path)) {
    redirect("/");
  }

  return (
    <SidebarProvider>
      <NavigationProgress />
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:font-medium focus:text-primary-foreground"
        href="#admin-main"
      >
        Skip to main content
      </a>
      <GlobalSidebar
        userEmail={me.email}
        userName={me.full_name ?? me.email}
        userRole={me.role}
      >
        {/* `display: contents` keeps the skip-link anchor present in the
            accessibility tree without inserting a real layout box, so the
            <SidebarInset> flex column still propagates flex-1 to the page
            outer wrappers below. */}
        <div className="contents" id="admin-main">
          {children}
        </div>
      </GlobalSidebar>
    </SidebarProvider>
  );
}
