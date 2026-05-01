import { SidebarProvider } from "@repo/design-system/components/ui/sidebar";
import { headers } from "next/headers";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
import { ApiError, fetchAdminMe } from "@/lib/api";
import { canAccessPath } from "@/lib/role-policy";
import { createSupabaseServerClient } from "@/lib/supabase/server";
import { GlobalSidebar } from "./components/sidebar";

export default async function AuthenticatedLayout({
  children,
}: {
  children: ReactNode;
}) {
  const supabase = await createSupabaseServerClient();
  const {
    data: { user },
  } = await supabase.auth.getUser();

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
      <a
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-primary focus:px-3 focus:py-2 focus:text-primary-foreground focus:font-medium"
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
