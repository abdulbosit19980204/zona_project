"use client";

import { AnimatePresence, motion } from "framer-motion";
import { ChevronDown, ChevronsLeft, ChevronsRight, MonitorCog } from "lucide-react";
import Link from "next/link";
import { useId } from "react";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { useQuery } from "@tanstack/react-query";

import { supportApi } from "@/components/support/api";
import { api } from "@/lib/api/client";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useOrg } from "@/hooks/use-org";
import { useQrNotifications } from "@/hooks/use-qrdrive";
import { activeNav, moduleOf, MODULES, type NavItem, type NavModule } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";

/** Foydali logosi: ko'k → binafsha gradient, "F" va StarGroup yulduzchasi (src/app/icon.svg bilan bir xil). */
export function LogoMark({ className }: { className?: string }) {
  const id = useId().replace(/:/g, "");
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={`lg${id}`} x1="0" y1="0" x2="64" y2="64" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#2f6feb" /><stop offset="1" stopColor="#6d4aff" />
        </linearGradient>
      </defs>
      <rect width="64" height="64" rx="16" fill={`url(#lg${id})`} />
      <rect x="17" y="14" width="9" height="36" rx="4.5" fill="#fff" />
      <rect x="17" y="14" width="28" height="9" rx="4.5" fill="#fff" />
      <rect x="17" y="29" width="19" height="8.5" rx="4.25" fill="#fff" />
      <path d="M48 35c1 4.6 2.8 6.4 7.4 7.4-4.6 1-6.4 2.8-7.4 7.4-1-4.6-2.8-6.4-7.4-7.4 4.6-1 6.4-2.8 7.4-7.4z" fill="#fff" fillOpacity=".92" />
    </svg>
  );
}

export function Brand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <LogoMark className="size-9 shrink-0 drop-shadow-[0_4px_12px_rgba(77,92,245,0.35)]" />
      {!collapsed && (
        <div className="min-w-0 leading-tight">
          <div className="text-[17px] font-bold tracking-tight">Foydali</div>
          <div className="mt-0.5 text-[10.5px] text-muted-foreground">StarGroup · IT platforma</div>
        </div>
      )}
    </div>
  );
}

const WARN_KEYS = new Set(["gaps", "qrErrors", "prbcControl"]);
const PRIMARY_KEYS = new Set(["approvals", "qrRequests"]);

function NavLink({ item, active, count, collapsed }: { item: NavItem; active: boolean; count?: number; collapsed: boolean }) {
  const t = useTranslations("nav");
  const link = (
    <Link
      href={item.href}
      className={cn(
        "group relative flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
        active && "bg-sidebar-accent text-foreground",
        collapsed && "justify-center px-0",
      )}
    >
      {active && <motion.span layoutId="nav-active" className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-primary" />}
      <item.icon className={cn("size-4 shrink-0", active && "text-primary")} />
      {!collapsed && <span className="truncate">{t(item.key)}</span>}
      {!collapsed && count !== undefined && (
        <span className={cn("ml-auto font-mono text-[11px]",
          WARN_KEYS.has(item.key) ? "text-warning" : PRIMARY_KEYS.has(item.key) ? "text-primary" : "text-muted-foreground")}>
          {count}
        </span>
      )}
      {collapsed && count !== undefined && item.key !== "employees" && (
        <span className="absolute right-2 top-1.5 size-1.5 rounded-full bg-warning" />
      )}
    </Link>
  );
  return collapsed ? (
    <Tooltip>
      <TooltipTrigger asChild>{link}</TooltipTrigger>
      <TooltipContent side="right">{t(item.key)}</TooltipContent>
    </Tooltip>
  ) : link;
}

function ModuleSection({ module, counts, down }: { module: NavModule; counts: Record<string, number | undefined>; down: boolean }) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const collapsed = useUI((s) => s.sidebarCollapsed);
  const closed = useUI((s) => s.closedModules.includes(module.key));
  const toggle = useUI((s) => s.toggleModule);
  const { model } = useOrg();
  const can = model?.state.me.can;
  const active = activeNav(pathname);
  const isCurrent = moduleOf(pathname).key === module.key;
  const open = collapsed || !closed;  // foydalanuvchi har bir modulni erkin yopadi/ochadi
  const Icon = module.icon;

  return (
    <div className="mb-2">
      {collapsed ? (
        <Tooltip>
          <TooltipTrigger asChild>
            <div className={cn("mx-auto my-2 grid size-8 place-items-center rounded-lg border", isCurrent ? "border-primary/40 text-primary" : "text-muted-foreground")}>
              <Icon className="size-4" />
            </div>
          </TooltipTrigger>
          <TooltipContent side="right">{t(`modules.${module.key}`)}</TooltipContent>
        </Tooltip>
      ) : (
        <button
          onClick={() => toggle(module.key)}
          className={cn(
            "flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left text-[13px] font-semibold transition-colors hover:bg-sidebar-accent",
            isCurrent && "text-foreground",
          )}
          aria-expanded={open}
        >
          <span className={cn("grid size-6 place-items-center rounded-md", isCurrent ? "bg-primary/15 text-primary" : "bg-muted text-muted-foreground")}>
            <Icon className="size-3.5" />
          </span>
          <span className="truncate">{t(`modules.${module.key}`)}</span>
          {down && <span className="size-1.5 rounded-full bg-warning" title={t("serviceDown")} />}
          <ChevronDown className={cn("ml-auto size-3.5 text-muted-foreground transition-transform", !open && "-rotate-90")} />
        </button>
      )}
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }} animate={{ height: "auto", opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.18 }} className={cn("overflow-hidden", !collapsed && "ml-3 border-l pl-2")}
          >
            {module.groups.map((group) => {
              const items = group.items.filter((i) => !i.perm || (can && (i.perm === "admin" ? can.admin : can.edit)));
              if (!items.length) return null;
              return (
                <div key={group.key} className="mb-1.5">
                  {!collapsed && (
                    <div className="px-2.5 pb-1 pt-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/70">
                      {t(`groups.${group.key}`)}
                    </div>
                  )}
                  {items.map((item) => (
                    <NavLink key={item.href} item={item} active={active?.href === item.href} count={counts[item.key]} collapsed={collapsed} />
                  ))}
                </div>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

/** Servislar boshqaruv markazi — alohida servis (lokalda :8900, serverda /control/). */
export function controlCenterUrl(): string {
  if (process.env.NEXT_PUBLIC_CONTROL_URL) return process.env.NEXT_PUBLIC_CONTROL_URL;
  if (typeof window === "undefined") return "/control/";
  return window.location.port === "3000" || window.location.hostname === "localhost"
    ? `${window.location.protocol}//${window.location.hostname}:8900/` : "/control/";
}

function ControlCenterLink({ collapsed }: { collapsed: boolean }) {
  const t = useTranslations("nav");
  const link = (
    <a href={controlCenterUrl()} target="_blank" rel="noreferrer" title={t("controlCenterHint")}
      className={cn("mx-3 mb-2 flex h-9 items-center gap-3 rounded-lg border border-dashed px-2.5 text-sm text-muted-foreground hover:border-primary/40 hover:text-foreground",
        collapsed && "justify-center px-0")}>
      <MonitorCog className="size-4 shrink-0" />
      {!collapsed && <span className="truncate">{t("controlCenter")}</span>}
    </a>
  );
  return collapsed ? (
    <Tooltip><TooltipTrigger asChild>{link}</TooltipTrigger><TooltipContent side="right">{t("controlCenter")}</TooltipContent></Tooltip>
  ) : link;
}

/** Chap menyu: har bir loyiha alohida ochiladigan menyu (ichida bo'limlari). Yig'iladi (tooltip bilan). */
export function Sidebar() {
  const t = useTranslations("nav");
  const collapsed = useUI((s) => s.sidebarCollapsed);
  const toggle = useUI((s) => s.toggleSidebar);
  const org = useOrg();
  const model = org.model;
  const qr = useQrNotifications();
  const pathname = usePathname();
  // support bo'limida: javob kutayotgan savollar va tasdiqlash navbati (support sahifalari bilan bitta kesh)
  const sup = useQuery({ queryKey: ["support", "stats"], queryFn: () => supportApi.stats(7), refetchInterval: 30_000,
    enabled: pathname === "/support" || pathname.startsWith("/support/") });
  const ss = sup.data;
  // PRBC bo'limida: ochiq vazifalar soni (nazorat sahifasi bilan bitta kesh)
  const prbc = useQuery({ queryKey: ["prbc", "control"], refetchInterval: 15_000,
    queryFn: async () => (await api.get<{ summary: { open: number } }>("prbc/control/")).data,
    enabled: Boolean(model?.state.me.can?.admin) && (pathname === "/prbc" || pathname.startsWith("/prbc/")
      || pathname === "/support" || pathname.startsWith("/support/")) });
  const counts: Record<string, number | undefined> = {
    supInbox: ss ? (ss.by_status.escalated ?? 0) + (ss.by_status.drafted ?? 0) || undefined : undefined,
    supReview: ss ? (ss.entries.new ?? 0) + (ss.entries.review ?? 0) + (ss.pending_edits ?? 0) || undefined : undefined,
    approvals: model?.state.meta.pending_approvals || undefined,
    gaps: model ? model.issueProcesses.length + (model.unassignedTasks.length ? 1 : 0) || undefined : undefined,
    employees: model?.state.members.length,
    qrRequests: qr.data?.pending_requests || undefined,
    qrErrors: qr.data?.failed_files || undefined,
    prbcControl: prbc.data?.summary.open || undefined,
  };
  const down: Record<string, boolean> = { zona: org.isError, qrdrive: qr.isError };

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 264 }}
      transition={{ type: "spring", stiffness: 380, damping: 36 }}
      className="flex h-full shrink-0 flex-col border-r bg-sidebar"
    >
      <div className={cn("flex h-16 items-center border-b px-4", collapsed && "justify-center px-0")}>
        <Brand collapsed={collapsed} />
      </div>
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-3">
        {MODULES.filter((m) => m.key !== "inventory" || (model?.state.me && !model.state.me.anonymous && model.state.me.inventory))
          .map((m) => <ModuleSection key={m.key} module={m} counts={counts} down={down[m.key]} />)}
      </nav>
      <ControlCenterLink collapsed={collapsed} />
      <button
        onClick={toggle}
        className={cn("flex h-11 items-center gap-2 border-t px-5 text-xs text-muted-foreground hover:text-foreground", collapsed && "justify-center px-0")}
        aria-label={t("toggle")}
      >
        {collapsed ? <ChevronsRight className="size-4" /> : <><ChevronsLeft className="size-4" />{t("collapse")}</>}
      </button>
    </motion.aside>
  );
}
