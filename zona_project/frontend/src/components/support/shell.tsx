"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, BookOpenCheck, BotMessageSquare, CheckCircle2, ChevronRight, Circle, Images, Inbox, Settings2 } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, type Mode } from "./api";
import { useSt, type SKey } from "./i18n";

const TABS: { href: string; key: SKey; icon: typeof Inbox; admin?: boolean }[] = [
  { href: "/support", key: "tabInbox", icon: Inbox },
  { href: "/support/review", key: "tabReview", icon: BookOpenCheck },
  { href: "/support/knowledge", key: "tabKnowledge", icon: BotMessageSquare },
  { href: "/support/images", key: "tabImages", icon: Images },
  { href: "/support/analytics", key: "tabAnalytics", icon: BarChart3 },
  { href: "/support/settings", key: "tabSettings", icon: Settings2, admin: true },
];

const MODE_DOT: Record<Mode, string> = { live: "bg-success", shadow: "bg-violet-500", collect: "bg-sky-500", off: "bg-muted-foreground/50" };

const isActive = (href: string, pathname: string) => (href === "/support" ? pathname === "/support" : pathname.startsWith(href));

/**
 * Support bo'limining umumiy qobig'i. Yuqorida — ixcham sarlavha, bot holati va bo'limlar menyusi (sanoqlar bilan);
 * pastda — aylanadigan tarkib. `fill` — tarkib butun balandlikni egallaydi (masalan, savollar suhbati).
 */
export function SupportShell({ title, description, actions, children, fill }: {
  title: string; description?: string; actions?: ReactNode; children: ReactNode; fill?: boolean;
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
  const Icon = TABS.find((x) => isActive(x.href, pathname))?.icon ?? BotMessageSquare;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="shrink-0 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <div className="mx-auto flex w-full max-w-[1600px] flex-wrap items-center gap-x-3 gap-y-2 px-4 pt-4 sm:px-6 lg:px-8">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary/20 to-violet-500/20 text-primary">
            <Icon className="size-[18px]" />
          </span>
          <div className="min-w-0 flex-1">
            <h1 className="truncate text-base font-semibold leading-tight tracking-tight sm:text-lg">{title}</h1>
            {description && <p className="truncate text-xs text-muted-foreground" title={description}>{description}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
          {bot ? (
            <Link href={can.admin ? "/support/settings" : "#"}
              className="flex shrink-0 items-center gap-2 rounded-full border bg-card py-1 pl-2.5 pr-3 text-xs shadow-xs transition-colors hover:bg-muted"
              title={bot.last_error || undefined}>
              <span className="relative flex size-2">
                {bot.enabled && bot.mode === "live" && !bot.last_error && <span className="absolute inline-flex size-full animate-ping rounded-full bg-success/60" />}
                <span className={cn("relative inline-flex size-2 rounded-full", bot.last_error || !bot.enabled ? "bg-warning" : MODE_DOT[bot.mode])} />
              </span>
              <span className="font-medium">{bot.username ? `@${bot.username}` : bot.name}</span>
              <span className="hidden text-muted-foreground sm:inline">{t(`mode_${bot.mode}` as SKey)}</span>
            </Link>
          ) : s && (
            <Link href="/support/settings" className="rounded-full border border-warning/40 bg-warning/10 px-3 py-1 text-xs text-warning">{t("botMissing")}</Link>
          )}
        </div>
        <nav className="mx-auto flex w-full max-w-[1600px] gap-1 overflow-x-auto px-3 pt-3 sm:px-5 lg:px-7" aria-label={t("tabsLabel")}>
          {TABS.filter((x) => !x.admin || can.admin).map((x) => {
            const active = isActive(x.href, pathname);
            const n = counts[x.key];
            return (
              <Link key={x.href} href={x.href} aria-current={active ? "page" : undefined}
                className={cn("group relative flex shrink-0 items-center gap-2 px-2.5 pb-2.5 pt-1.5 text-[13px] transition-colors",
                  active ? "font-medium text-foreground" : "text-muted-foreground hover:text-foreground")}>
                <span className={cn("grid size-6 place-items-center rounded-md transition-colors",
                  active ? "bg-primary text-primary-foreground" : "bg-muted group-hover:bg-muted-foreground/15")}>
                  <x.icon className="size-3.5" />
                </span>
                {t(x.key)}
                {!!n && <span className="rounded-full bg-warning/15 px-1.5 text-[10px] font-semibold tabular-nums text-warning">{n}</span>}
                {active && <span className="absolute inset-x-1.5 -bottom-px h-0.5 rounded-full bg-primary" />}
              </Link>
            );
          })}
        </nav>
      </header>
      <div className={cn("min-h-0 flex-1", fill ? "flex flex-col" : "overflow-y-auto")}>
        <div className={cn("mx-auto w-full max-w-[1600px] px-4 py-5 sm:px-6 lg:px-8", fill && "flex min-h-0 flex-1 flex-col")}>
          {can.admin && pathname === "/support" && <SetupGuide />}
          {children}
        </div>
      </div>
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
  const done = steps.filter((x) => x.done).length;
  if (done === steps.length) return null;
  return (
    <div className="mb-4 shrink-0 rounded-xl border border-primary/25 bg-gradient-to-r from-primary/[0.07] to-violet-500/[0.05] p-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="text-sm font-semibold">{t("setupTitle")}</div>
        <div className="h-1.5 w-28 overflow-hidden rounded-full bg-primary/15">
          <div className="h-full rounded-full bg-primary" style={{ width: `${(100 * done) / steps.length}%` }} />
        </div>
        <span className="text-xs text-muted-foreground">{t("setupProgress", { d: done, n: steps.length })}</span>
        <Link href="/support/settings" className="ml-auto inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">
          {t("setupOpen")}<ChevronRight className="size-4" />
        </Link>
      </div>
      <ol className="mt-3 flex flex-wrap gap-2">
        {steps.map((x) => (
          <li key={x.key} className={cn("flex items-center gap-1.5 rounded-full border bg-background/70 px-2.5 py-1 text-xs",
            x.done && "text-muted-foreground line-through")}>
            {x.done ? <CheckCircle2 className="size-3.5 text-success" /> : <Circle className="size-3.5 text-primary" />}
            {t(x.key)}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** Sozlamalar qatori: nom va izoh chapda, boshqaruv o'ngda — o'qish va bosish oson. */
export function SettingRow({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex items-start justify-between gap-4 border-b py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="min-w-0">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{hint}</div>}
      </div>
      <div className="shrink-0">{children}</div>
    </div>
  );
}
