import {
  Activity, BadgeCheck, Bot, Building2, ChartColumn, ChartPie, FileChartColumn, FolderOpen, Gauge, Grid3x3, HardDrive, History,
  LayoutDashboard, ListChecks, MessageCircleQuestion, Network, Orbit, PlugZap, QrCode, ScrollText, Settings, ShieldAlert,
  Signpost, TriangleAlert, UserPlus, Users, UsersRound, Wand2, Workflow, type LucideIcon,
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

/** Masʼuliyat platformasi (Zona) menyusi: MAIN · MANAGEMENT · ANALYTICS · SYSTEM. */
export const NAV: NavGroup[] = [
  {
    key: "main",
    items: [
      { href: "/", key: "overview", icon: LayoutDashboard },
      { href: "/organization", key: "organization", icon: Network },
      { href: "/responsibility-map", key: "responsibilityMap", icon: Orbit },
      { href: "/departments", key: "departments", icon: Building2 },
      { href: "/employees", key: "employees", icon: Users },
      { href: "/staff", key: "staff", icon: UsersRound },
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

/** QR Drive mikroservisi menyusi (alohida servis — ishlamasa ham Zona menyusi ishlaydi). */
export const QR_NAV: NavGroup[] = [
  {
    key: "qrMain",
    items: [
      { href: "/qr", key: "qrOverview", icon: QrCode },
      { href: "/qr/files", key: "qrFiles", icon: FolderOpen },
      { href: "/qr/employees", key: "qrEmployees", icon: Users },
      { href: "/qr/requests", key: "qrRequests", icon: UserPlus },
    ],
  },
  {
    key: "qrReliability",
    items: [
      { href: "/qr/analytics", key: "qrAnalytics", icon: ChartPie },
      { href: "/qr/errors", key: "qrErrors", icon: TriangleAlert },
      { href: "/qr/audit", key: "qrAudit", icon: ScrollText },
      { href: "/qr/system", key: "qrSystem", icon: Activity },
    ],
  },
  {
    key: "qrConfig",
    items: [
      { href: "/qr/storages", key: "qrStorages", icon: HardDrive },
      { href: "/qr/settings", key: "qrSettings", icon: Bot },
      { href: "/qr/api", key: "qrApi", icon: PlugZap },
      { href: "/qr/setup", key: "qrSetup", icon: Wand2 },
    ],
  },
];

export interface NavModule {
  key: "zona" | "qrdrive"; // nav.modules.<key>
  icon: LucideIcon;
  groups: NavGroup[];
}

/** Chap menyu: har bir loyiha (vazifa) — alohida ochiladigan menyu, ichida o'z bo'limlari. */
export const MODULES: NavModule[] = [
  { key: "zona", icon: Orbit, groups: NAV },
  { key: "qrdrive", icon: QrCode, groups: QR_NAV },
];

export const ALL_NAV = MODULES.flatMap((m) => m.groups.flatMap((g) => g.items));

export function activeNav(pathname: string): NavItem | undefined {
  if (pathname === "/") return ALL_NAV[0];
  return ALL_NAV.filter((i) => i.href !== "/" && (pathname === i.href || pathname.startsWith(i.href + "/")))
    .sort((a, b) => b.href.length - a.href.length)[0];
}

export function moduleOf(pathname: string): NavModule {
  return pathname === "/qr" || pathname.startsWith("/qr/") ? MODULES[1] : MODULES[0];
}

export function groupOf(item: NavItem | undefined): { module: NavModule; group: NavGroup } | undefined {
  for (const mod of MODULES) {
    const group = mod.groups.find((g) => item && g.items.includes(item));
    if (group) return { module: mod, group };
  }
  return undefined;
}
