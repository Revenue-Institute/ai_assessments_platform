import type { AdminRole } from "./api";

/** Path-prefix to the minimum role required to view that route.
 * Order matters: longer prefixes win. Routes not listed default to "viewer". */
const ROUTE_MIN_ROLE: Array<{ prefix: string; role: AdminRole }> = [
  { prefix: "/modules/new", role: "admin" },
  { prefix: "/assessments/new", role: "admin" },
  { prefix: "/assignments/new", role: "admin" },
  { prefix: "/settings/users", role: "admin" },
  { prefix: "/settings", role: "admin" },
  { prefix: "/series", role: "reviewer" },
  { prefix: "/references", role: "reviewer" },
  { prefix: "/cohorts", role: "reviewer" },
  { prefix: "/modules", role: "viewer" },
  { prefix: "/assessments", role: "viewer" },
  { prefix: "/assignments", role: "viewer" },
  { prefix: "/subjects", role: "viewer" },
  { prefix: "/competencies", role: "viewer" },
];

const ROLE_RANK: Record<AdminRole, number> = {
  viewer: 0,
  reviewer: 1,
  admin: 2,
};

export function minimumRoleForPath(path: string): AdminRole {
  const sorted = [...ROUTE_MIN_ROLE].sort(
    (a, b) => b.prefix.length - a.prefix.length,
  );
  for (const entry of sorted) {
    if (path === entry.prefix || path.startsWith(`${entry.prefix}/`)) {
      return entry.role;
    }
  }
  return "viewer";
}

export function roleSatisfies(role: AdminRole, required: AdminRole): boolean {
  return ROLE_RANK[role] >= ROLE_RANK[required];
}

export function canAccessPath(role: AdminRole, path: string): boolean {
  return roleSatisfies(role, minimumRoleForPath(path));
}
