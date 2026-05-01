"use client";

import { ModeToggle } from "@repo/design-system/components/mode-toggle";
import { Button } from "@repo/design-system/components/ui/button";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
} from "@repo/design-system/components/ui/sidebar";
import {
  BookOpenIcon,
  ClipboardListIcon,
  FilesIcon,
  GaugeIcon,
  LayersIcon,
  LayoutDashboardIcon,
  LibraryIcon,
  LogOutIcon,
  RepeatIcon,
  SettingsIcon,
  TagsIcon,
  UsersIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import type { AdminRole } from "@/lib/api";
import { canAccessPath } from "@/lib/role-policy";
import { signOut } from "../../(unauthenticated)/sign-in/actions";

const NAV_PRIMARY = [
  { title: "Dashboard", href: "/", icon: LayoutDashboardIcon },
  { title: "Modules", href: "/modules", icon: BookOpenIcon },
  { title: "Assessments", href: "/assessments", icon: FilesIcon },
  { title: "Candidates", href: "/candidates", icon: UsersIcon },
  { title: "Assignments", href: "/assignments", icon: ClipboardListIcon },
  { title: "Cohorts", href: "/cohorts", icon: GaugeIcon },
  { title: "Series", href: "/series", icon: RepeatIcon },
] as const;

const NAV_LIBRARY = [
  { title: "References", href: "/references", icon: LibraryIcon },
  { title: "Competencies", href: "/competencies", icon: TagsIcon },
] as const;

const NAV_SETTINGS = [
  { title: "Users", href: "/settings/users", icon: SettingsIcon },
] as const;

type GlobalSidebarProps = {
  children: ReactNode;
  userEmail: string;
  userName: string;
  userRole: AdminRole;
};

export function GlobalSidebar({
  children,
  userEmail,
  userName,
  userRole,
}: GlobalSidebarProps) {
  const pathname = usePathname();
  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname?.startsWith(href);
  const visiblePrimary = NAV_PRIMARY.filter((item) =>
    canAccessPath(userRole, item.href),
  );
  const visibleLibrary = NAV_LIBRARY.filter((item) =>
    canAccessPath(userRole, item.href),
  );
  const visibleSettings = NAV_SETTINGS.filter((item) =>
    canAccessPath(userRole, item.href),
  );

  async function handleSignOut() {
    await signOut();
    window.location.href = "/sign-in";
  }

  return (
    <>
      <Sidebar variant="inset">
        <SidebarHeader>
          <div className="flex items-center gap-2 px-2 py-1.5">
            <LayersIcon className="h-5 w-5 text-primary" />
            <span className="font-medium text-sm">RI Assessments</span>
          </div>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupLabel>Operate</SidebarGroupLabel>
            <SidebarMenu>
              {visiblePrimary.map((item) => (
                <SidebarMenuItem key={item.href}>
                  <SidebarMenuButton
                    asChild
                    isActive={isActive(item.href)}
                    tooltip={item.title}
                  >
                    <Link href={item.href}>
                      <item.icon />
                      <span>{item.title}</span>
                    </Link>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroup>

          {visibleLibrary.length > 0 && (
            <SidebarGroup>
              <SidebarGroupLabel>Library</SidebarGroupLabel>
              <SidebarMenu>
                {visibleLibrary.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(item.href)}
                      tooltip={item.title}
                    >
                      <Link href={item.href}>
                        <item.icon />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroup>
          )}

          {visibleSettings.length > 0 && (
            <SidebarGroup className="mt-auto">
              <SidebarGroupLabel>Settings</SidebarGroupLabel>
              <SidebarMenu>
                {visibleSettings.map((item) => (
                  <SidebarMenuItem key={item.href}>
                    <SidebarMenuButton
                      asChild
                      isActive={isActive(item.href)}
                      tooltip={item.title}
                    >
                      <Link href={item.href}>
                        <item.icon />
                        <span>{item.title}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroup>
          )}
        </SidebarContent>
        <SidebarFooter>
          <div className="flex flex-col gap-2 px-2 py-1.5">
            <div className="flex flex-col">
              <span className="truncate font-medium text-sm">{userName}</span>
              <span className="truncate text-muted-foreground text-xs">
                {userEmail}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <ModeToggle />
              <Button
                onClick={handleSignOut}
                size="sm"
                title="Sign out"
                variant="ghost"
              >
                <LogOutIcon className="h-4 w-4" />
                <span className="sr-only">Sign out</span>
              </Button>
            </div>
          </div>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>{children}</SidebarInset>
    </>
  );
}
