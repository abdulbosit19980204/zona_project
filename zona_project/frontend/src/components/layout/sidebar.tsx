"use client";

import { motion } from "framer-motion";
import { ChevronsLeft, ChevronsRight } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTranslations } from "next-intl";

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useModel } from "@/hooks/use-org";
import { activeNav, NAV } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";

export function Brand({ collapsed = false }: { collapsed?: boolean }) {
  return (
    <div className="flex items-center gap-3">
      <span className="relative grid size-9 shrink-0 place-items-center rounded-xl border bg-gradient-to-br from-elevated to-card">
        <span className="size-2.5 rounded-full bg-primary shadow-[0_0_0_4px_color-mix(in_srgb,var(--primary)_18%,transparent),0_0_16px_var(--primary)]" />
        <span className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-violet" />
      </span>
      {!collapsed && (
        <div className="min-w-0 leading-tight">
          <div className="text-[13px] font-bold uppercase tracking-[0.08em]">Responsibility<br />Architecture</div>
          <div className="mt-0.5 text-[10.5px] text-muted-foreground">Clear Ownership. Better Execution.</div>
        </div>
      )}
    </div>
  );
}

/** Chap menyu: yig'iladi (tooltip bilan), faol bo'lim chiziq bilan belgilanadi. */
export function Sidebar() {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const collapsed = useUI((s) => s.sidebarCollapsed);
  const toggle = useUI((s) => s.toggleSidebar);
  const model = useModel();
  const can = model.state.me.can;
  const active = activeNav(pathname);
  const counts: Record<string, number | undefined> = {
    approvals: model.state.meta.pending_approvals || undefined,
    gaps: model.issueProcesses.length + (model.unassignedTasks.length ? 1 : 0) || undefined,
    employees: model.state.members.length,
  };

  return (
    <motion.aside
      animate={{ width: collapsed ? 72 : 256 }}
      transition={{ type: "spring", stiffness: 380, damping: 36 }}
      className="flex h-full shrink-0 flex-col border-r bg-sidebar"
    >
      <div className={cn("flex h-16 items-center border-b px-4", collapsed && "justify-center px-0")}>
        <Brand collapsed={collapsed} />
      </div>
      <nav className="flex-1 overflow-y-auto overflow-x-hidden px-3 py-3">
        {NAV.map((group) => {
          const items = group.items.filter((i) => !i.perm || (i.perm === "admin" ? can.admin : can.edit));
          return (
            <div key={group.key} className="mb-3">
              {!collapsed && (
                <div className="px-2.5 pb-1.5 pt-3 text-[10.5px] font-semibold uppercase tracking-[0.12em] text-muted-foreground/70">
                  {t(`groups.${group.key}`)}
                </div>
              )}
              {collapsed && <div className="mx-auto my-2 h-px w-6 bg-border" />}
              {items.map((item) => {
                const isActive = active?.href === item.href;
                const count = counts[item.key];
                const link = (
                  <Link
                    href={item.href}
                    className={cn(
                      "group relative flex h-9 items-center gap-3 rounded-lg px-2.5 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground",
                      isActive && "bg-sidebar-accent text-foreground",
                      collapsed && "justify-center px-0",
                    )}
                  >
                    {isActive && (
                      <motion.span layoutId="nav-active" className="absolute inset-y-1.5 left-0 w-0.5 rounded-full bg-primary" />
                    )}
                    <item.icon className={cn("size-4 shrink-0", isActive && "text-primary")} />
                    {!collapsed && <span className="truncate">{t(item.key)}</span>}
                    {!collapsed && count !== undefined && (
                      <span
                        className={cn(
                          "ml-auto font-mono text-[11px]",
                          item.key === "gaps" ? "text-warning" : item.key === "approvals" ? "text-primary" : "text-muted-foreground",
                        )}
                      >
                        {count}
                      </span>
                    )}
                    {collapsed && count !== undefined && item.key !== "employees" && (
                      <span className="absolute right-2 top-1.5 size-1.5 rounded-full bg-warning" />
                    )}
                  </Link>
                );
                return collapsed ? (
                  <Tooltip key={item.href}>
                    <TooltipTrigger asChild>{link}</TooltipTrigger>
                    <TooltipContent side="right">{t(item.key)}</TooltipContent>
                  </Tooltip>
                ) : (
                  <div key={item.href}>{link}</div>
                );
              })}
            </div>
          );
        })}
      </nav>
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
