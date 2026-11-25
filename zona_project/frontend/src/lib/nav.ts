import {
  Activity, BadgeCheck, BookOpen, ClipboardCheck, FileSpreadsheet, KeyRound, Laptop, Smartphone, BookOpenCheck, Bot, BotMessageSquare, Building2, ChartColumn, ChartPie, FileChartColumn, FolderOpen, Gauge, Grid3x3, HardDrive, History, LayoutDashboard, ListChecks, MessageCircleQuestion, Network, Orbit, PlugZap, QrCode, ScrollText, Settings, ShieldAlert, Inbox, Signpost, Sparkles, SlidersHorizontal, TriangleAlert, UserPlus, Users, UsersRound, Wand2, Workflow, RefreshCcwDot, type LucideIcon,
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
      { href: "/ai-history", key: "aiHistory", icon: Sparkles },
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

/** Support bot: Telegram guruhlaridagi savollarga avto-javob, bilim bazasi va tasdiqlash. */
export const SUPPORT_NAV: NavGroup[] = [
  {
    key: "supMain",
    items: [
      { href: "/support", key: "supInbox", icon: Inbox },
      { href: "/support/review", key: "supReview", icon: BookOpenCheck },
      { href: "/support/knowledge", key: "supKnowledge", icon: BotMessageSquare },
      { href: "/support/images", key: "supImages", icon: QrCode },
      { href: "/support/analytics", key: "supAnalytics", icon: ChartColumn },
      { href: "/support/explore", key: "supExplore", icon: Grid3x3 },
    ],
  },
  {
    key: "supTasks",
    items: [
      { href: "/prbc", key: "prbcControl", icon: Gauge, perm: "admin" },
      { href: "/prbc/tasks", key: "prbcTasks", icon: ListChecks, perm: "admin" },
      { href: "/prbc/people", key: "prbcPeople", icon: UsersRound, perm: "admin" },
      { href: "/prbc/log", key: "prbcLog", icon: ScrollText, perm: "admin" },
    ],
  },
  {
    key: "supConfig",
    items: [
      { href: "/support/settings", key: "supSettings", icon: SlidersHorizontal, perm: "admin" },
      { href: "/prbc/settings", key: "prbcSettings", icon: RefreshCcwDot, perm: "admin" },
    ],
  },
];

/** IT inventarizatsiya: alohida mustaqil sahifa (/inventory) — faqat huquqi borlarga ko'rinadi. */
export const INVENTORY_NAV: NavGroup[] = [
  {
    key: "invMain",
    items: [
      { href: "/inv", key: "invOverview", icon: ChartColumn },
      { href: "/inv/items", key: "invItems", icon: Laptop },
      { href: "/inv/employees", key: "invEmployees", icon: Users },
      { href: "/inv/branches", key: "invBranches", icon: Building2 },
      { href: "/inv/history", key: "invHistory", icon: History },
    ],
  },
  {
    key: "invConfig",
    items: [
      { href: "/inv/exchange", key: "invExchange", icon: FileSpreadsheet },
      { href: "/inv/users", key: "invUsers", icon: KeyRound, perm: "admin" },
      { href: "/inv/catalog", key: "invCatalog", icon: SlidersHorizontal, perm: "admin" },
      { href: "/inventory?mobile=1", key: "invMobile", icon: Smartphone },
    ],
  },
];

/** Qo'llanma: butun tizimning yo'riqnomasi (docs/manual/*.md) — har bob alohida. */
export const DOCS_NAV: NavGroup[] = [
  {
    key: "docsMain",
    items: [
      { href: "/docs", key: "docsOverview", icon: BookOpen },
      { href: "/docs/support-bot", key: "docsSupport", icon: BotMessageSquare },
      { href: "/docs/prbc", key: "docsPrbc", icon: RefreshCcwDot },
      { href: "/docs/inventarizatsiya", key: "docsInventory", icon: ClipboardCheck },
      { href: "/docs/zona", key: "docsZona", icon: Orbit },
      { href: "/docs/sozlamalar", key: "docsSettings", icon: SlidersHorizontal },
      { href: "/docs/texnik", key: "docsTech", icon: Settings },
      { href: "/docs/ozgarishlar", key: "docsChanges", icon: History },
    ],
  },
];

export interface NavModule {
  key: "zona" | "qrdrive" | "support" | "inventory" | "docs"; // nav.modules.<key>
  icon: LucideIcon;
  groups: NavGroup[];
}

/** Chap menyu: har bir loyiha (vazifa) — alohida ochiladigan menyu, ichida o'z bo'limlari. */
export const MODULES: NavModule[] = [
  { key: "zona", icon: Orbit, groups: NAV },
  { key: "qrdrive", icon: QrCode, groups: QR_NAV },
  { key: "support", icon: BotMessageSquare, groups: SUPPORT_NAV },
  { key: "inventory", icon: ClipboardCheck, groups: INVENTORY_NAV },
  { key: "docs", icon: BookOpen, groups: DOCS_NAV },
];

export const ALL_NAV = MODULES.flatMap((m) => m.groups.flatMap((g) => g.items));

export function activeNav(pathname: string): NavItem | undefined {
  if (pathname === "/") return ALL_NAV[0];
  return ALL_NAV.filter((i) => i.href !== "/" && (pathname === i.href || pathname.startsWith(i.href + "/")))
    .sort((a, b) => b.href.length - a.href.length)[0];
}

export function moduleOf(pathname: string): NavModule {
  if (pathname === "/qr" || pathname.startsWith("/qr/")) return MODULES[1];
  if (pathname === "/support" || pathname.startsWith("/support/") || pathname === "/prbc" || pathname.startsWith("/prbc/")) return MODULES[2];
  if (pathname === "/inv" || pathname.startsWith("/inv/")) return MODULES[3];
  if (pathname === "/docs" || pathname.startsWith("/docs/")) return MODULES[4];
  return MODULES[0];
}

export function groupOf(item: NavItem | undefined): { module: NavModule; group: NavGroup } | undefined {
  for (const mod of MODULES) {
    const group = mod.groups.find((g) => item && g.items.includes(item));
    if (group) return { module: mod, group };
  }
  return undefined;
}
