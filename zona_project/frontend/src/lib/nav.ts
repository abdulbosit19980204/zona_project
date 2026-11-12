import {
  BadgeCheck, Building2, ChartColumn, FileChartColumn, Gauge, Grid3x3, History, LayoutDashboard, ListChecks,
  MessageCircleQuestion, Network, Orbit, Settings, ShieldAlert, Signpost, Users, Workflow, type LucideIcon,
} from "lucide-react";

export interface NavItem {
  href: string;
  key: string; // tarjima kaliti: nav.<key>
  icon: LucideIcon;
  perm?: "edit" | "admin";
}

export interface NavGroup {
  key: string; // nav.groups.<key>
  items: NavItem[];
}

/** Chap menyu: MAIN · MANAGEMENT · ANALYTICS · SYSTEM. */
export const NAV: NavGroup[] = [
  {
    key: "main",
    items: [
      { href: "/", key: "overview", icon: LayoutDashboard },
      { href: "/organization", key: "organization", icon: Network },
      { href: "/responsibility-map", key: "responsibilityMap", icon: Orbit },
      { href: "/departments", key: "departments", icon: Building2 },
      { href: "/employees", key: "employees", icon: Users },
      { href: "/ask", key: "ask", icon: MessageCircleQuestion },
      { href: "/cheatsheet", key: "cheatsheet", icon: Signpost },
    ],
  },
  {
    key: "management",
    items: [
      { href: "/responsibilities", key: "responsibilities", icon: ListChecks },
      { href: "/processes", key: "processes", icon: Workflow },
      { href: "/matrix", key: "matrix", icon: Grid3x3 },
      { href: "/approvals", key: "approvals", icon: BadgeCheck },
    ],
  },
  {
    key: "analytics",
    items: [
      { href: "/analytics", key: "analytics", icon: ChartColumn },
      { href: "/workload", key: "workload", icon: Gauge },
      { href: "/gaps", key: "gaps", icon: ShieldAlert },
      { href: "/reports", key: "reports", icon: FileChartColumn },
    ],
  },
  {
    key: "system",
    items: [
      { href: "/audit", key: "audit", icon: History },
      { href: "/settings", key: "settings", icon: Settings },
    ],
  },
];

export const ALL_NAV = NAV.flatMap((g) => g.items);

export function activeNav(pathname: string): NavItem | undefined {
  if (pathname === "/") return ALL_NAV[0];
  return ALL_NAV.filter((i) => i.href !== "/" && pathname.startsWith(i.href)).sort((a, b) => b.href.length - a.href.length)[0];
}
