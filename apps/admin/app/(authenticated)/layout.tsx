import { SidebarProvider } from "@repo/design-system/components/ui/sidebar";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";
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

  return (
    <SidebarProvider>
      <GlobalSidebar
        userEmail={user.email ?? ""}
        userName={
          (user.user_metadata?.full_name as string | undefined) ??
          user.email ??
          ""
        }
      >
        {children}
      </GlobalSidebar>
    </SidebarProvider>
  );
}
