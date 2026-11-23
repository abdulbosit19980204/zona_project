"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, BookOpenCheck, BotMessageSquare, ChevronRight, Circle, Images, Inbox, Settings2, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

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
 * Support bo'limining umumiy qobig'i: bitta ixcham qator (sarlavha, amallar, bot holati) va aylanadigan tarkib.
 * Bo'limlar menyusi — chapdagi yig'iladigan asosiy menyuda (sanoqlar bilan), ekran ma'lumot uchun bo'sh qoladi.
 * `fill` — tarkib butun balandlikni egallaydi (masalan, savollar suhbati).
 */
export function SupportShell({ title, description, actions, children, fill }: {
  title: string; description?: string; actions?: ReactNode; children: ReactNode; fill?: boolean;
}) {
  const t = useSt();
  const pathname = usePathname();
  const can = useCan();
  const stats = useQuery({ queryKey: ["support", "stats"], queryFn: () => supportApi.stats(7), refetchInterval: 30_000 });
  const s = stats.data;
  const bot = s?.bots[0];
  const Icon = TABS.find((x) => isActive(x.href, pathname))?.icon ?? BotMessageSquare;

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="shrink-0 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <div className="mx-auto flex w-full max-w-[1800px] flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2 sm:px-5">
          <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary">
            <Icon className="size-4" />
          </span>
          <div className="flex min-w-0 flex-1 items-baseline gap-2">
            <h1 className="shrink-0 text-[15px] font-semibold leading-tight tracking-tight">{title}</h1>
            {description && <p className="hidden truncate text-xs text-muted-foreground lg:block" title={description}>{description}</p>}
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
      </header>
      <div className={cn("min-h-0 flex-1", fill ? "flex flex-col" : "overflow-y-auto")}>
        <div className={cn("mx-auto w-full max-w-[1800px] px-3 py-3 sm:px-5", fill && "flex min-h-0 flex-1 flex-col")}>
          {can.admin && pathname === "/support" && <SetupGuide />}
          {children}
        </div>
      </div>
    </div>
  );
}

const GUIDE_KEY = "support.setupGuide.hidden";

/** Sozlash yo'riqnomasi: bitta ixcham qator (qolgan qadamlar), yopib qo'yiladi; hammasi tayyor bo'lsa ko'rinmaydi. */
function SetupGuide() {
  const t = useSt();
  const [hidden, setHidden] = useState(() => {
    try { return localStorage.getItem(GUIDE_KEY) === "1"; } catch { return false; }
  });
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
  if (done === steps.length || hidden) return null;
  const hide = () => { setHidden(true); try { localStorage.setItem(GUIDE_KEY, "1"); } catch { /* saqlanmasa ham yopiladi */ } };
  return (
    <div className="mb-3 flex shrink-0 flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-primary/25 bg-primary/[0.05] px-3 py-1.5 text-xs">
      <span className="font-medium">{t("setupProgress", { d: done, n: steps.length })}</span>
      {steps.filter((x) => !x.done).map((x) => (
        <span key={x.key} className="inline-flex items-center gap-1 text-muted-foreground"><Circle className="size-3 text-primary" />{t(x.key)}</span>
      ))}
      <Link href="/support/settings" className="ml-auto inline-flex items-center gap-0.5 font-medium text-primary hover:underline">
        {t("setupOpen")}<ChevronRight className="size-3.5" />
      </Link>
      <button type="button" onClick={hide} className="rounded p-0.5 text-muted-foreground hover:bg-muted hover:text-foreground"
        aria-label={t("close")} title={t("close")}><X className="size-3.5" /></button>
    </div>
  );
}

/** Sozlamalar qatori: nom va izoh chapda, boshqaruv o'ngda — o'qish va bosish oson. */
export function SettingRow({ label, hint, children }: { label: string; hint?: ReactNode; children: ReactNode }) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-x-4 gap-y-2 border-b py-3 first:pt-0 last:border-b-0 last:pb-0">
      <div className="min-w-[12rem] flex-1">
        <div className="text-sm font-medium">{label}</div>
        {hint && <div className="mt-0.5 text-xs leading-relaxed text-muted-foreground">{hint}</div>}
      </div>
      <div className="max-w-full shrink-0">{children}</div>
    </div>
  );
}
