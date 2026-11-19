"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, BookOpenCheck, BotMessageSquare, CheckCircle2, Circle, Images, Inbox, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi } from "./api";
import { useSt, type SKey } from "./i18n";

const TABS: { href: string; key: SKey; icon: typeof Inbox; admin?: boolean }[] = [
  { href: "/support", key: "tabInbox", icon: Inbox },
  { href: "/support/review", key: "tabReview", icon: BookOpenCheck },
  { href: "/support/knowledge", key: "tabKnowledge", icon: BotMessageSquare },
  { href: "/support/images", key: "tabImages", icon: Images },
  { href: "/support/analytics", key: "tabAnalytics", icon: BarChart3 },
  { href: "/support/settings", key: "tabSettings", icon: Settings2, admin: true },
];

/**
 * Support bo'limining umumiy qobig'i: sarlavha, bo'limlar orasida tez o'tish (sanoqlar bilan), bot holati va
 * sozlash tugallanmagan bo'lsa — qadam-baqadam yo'riqnoma. Barcha support sahifalari shu qobiqda.
 */
export function SupportShell({ title, description, actions, children, wide }: {
  title: string; description?: string; actions?: ReactNode; children: ReactNode; wide?: boolean;
}) {
  const t = useSt();
  const pathname = usePathname();
  const can = useCan();
  const stats = useQuery({ queryKey: ["support", "stats"], queryFn: () => supportApi.stats(7), refetchInterval: 30_000 });
  const s = stats.data;
  const counts: Partial<Record<SKey, number>> = {
    tabInbox: (s?.by_status.escalated ?? 0) + (s?.by_status.drafted ?? 0),
    tabReview: (s?.entries.new ?? 0) + (s?.entries.review ?? 0) + (s?.pending_edits ?? 0),
  };
  const bot = s?.bots[0];

  return (
    <div className={cn("h-full overflow-y-auto", wide ? "px-0" : "px-4 py-5 sm:px-6 lg:px-8")}>
      <div className={cn(wide && "px-4 pt-5 sm:px-6 lg:px-8")}>
        <div className="mb-4 flex flex-wrap items-start gap-3">
          <div className="min-w-0 flex-1">
            <h1 className="text-xl font-semibold tracking-tight">{title}</h1>
            {description && <p className="mt-1 max-w-3xl text-sm text-muted-foreground">{description}</p>}
          </div>
          {bot && (
            <div className="flex items-center gap-2 rounded-full border bg-card px-3 py-1.5 text-xs">
              <span className={cn("size-2 rounded-full", bot.enabled && !bot.last_error ? "bg-success" : "bg-warning")} />
              <span className="font-medium">{bot.username ? `@${bot.username}` : bot.name}</span>
              <span className="text-muted-foreground">· {t(`mode_${bot.mode}` as SKey)}</span>
            </div>
          )}
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </div>
        <nav className="-mx-1 mb-5 flex gap-1 overflow-x-auto border-b pb-px" aria-label={t("tabsLabel")}>
          {TABS.filter((x) => !x.admin || can.admin).map((x) => {
            const active = x.href === "/support" ? pathname === "/support" : pathname.startsWith(x.href);
            const n = counts[x.key];
            return (
              <Link key={x.href} href={x.href}
                className={cn("relative flex shrink-0 items-center gap-1.5 rounded-t-md px-3 py-2 text-sm transition-colors",
                  active ? "font-medium text-foreground after:absolute after:inset-x-2 after:-bottom-px after:h-0.5 after:rounded-full after:bg-primary"
                    : "text-muted-foreground hover:text-foreground")}>
                <x.icon className="size-4" />{t(x.key)}
                {!!n && <span className="rounded-full bg-primary/15 px-1.5 text-[11px] font-semibold text-primary">{n}</span>}
              </Link>
            );
          })}
        </nav>
        {can.admin && pathname === "/support" && <SetupGuide />}
      </div>
      {children}
    </div>
  );
}

/** Sozlash yo'riqnomasi: hammasi tayyor bo'lsa ko'rinmaydi. */
function SetupGuide() {
  const t = useSt();
  const bots = useQuery({ queryKey: ["support", "bots"], queryFn: supportApi.bots });
  const groups = useQuery({ queryKey: ["support", "groups"], queryFn: supportApi.groups });
  if (!bots.data || !groups.data) return null;
  const bot = bots.data[0];
  const active = groups.data.filter((g) => g.is_active);
  const steps: { done: boolean; key: SKey }[] = [
    { done: !!bot, key: "stepBot" },
    { done: !!bot?.admin_chat_id, key: "stepAdminChat" },
    { done: active.length > 0, key: "stepGroup" },
    { done: active.length > 0 && active.every((g) => g.is_admin), key: "stepGroupAdmin" },
    { done: active.some((g) => g.effective_mode === "live"), key: "stepLive" },
  ];
  if (steps.every((x) => x.done)) return null;
  return (
    <div className="mb-5 rounded-xl border border-primary/30 bg-primary/5 p-4">
      <div className="mb-2 text-sm font-medium">{t("setupTitle")}</div>
      <ol className="grid gap-1.5 sm:grid-cols-2 lg:grid-cols-3">
        {steps.map((x) => (
          <li key={x.key} className={cn("flex items-start gap-2 text-sm", x.done && "text-muted-foreground line-through")}>
            {x.done ? <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-success" /> : <Circle className="mt-0.5 size-4 shrink-0 text-primary" />}
            {t(x.key)}
          </li>
        ))}
      </ol>
      <Link href="/support/settings" className="mt-3 inline-block text-sm font-medium text-primary hover:underline">{t("setupOpen")} →</Link>
    </div>
  );
}

/** Sozlamalar qatori: nom va izoh chapda, boshqaruv o'ngda — o'qish va bosish oson. */
export function SettingRow({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b py-3 last:border-b-0">
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-xs text-muted-foreground">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
