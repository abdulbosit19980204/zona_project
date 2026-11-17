"use client";

import { useQueryClient } from "@tanstack/react-query";
import { formatDistanceToNow } from "date-fns";
import { enUS, ru, uz } from "date-fns/locale";
import {
  Bell, Building2, Check, ChevronDown, Languages, Layers, LogOut, Monitor, Moon, Orbit, Plus, Search, Settings, Sun, User,
} from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useLocale, useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import { useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { QrBell } from "@/components/qrdrive/bell";
import { TaskDialog } from "@/components/forms/task-dialog";
import { CommandPalette } from "@/components/layout/command-palette";
import {
  Breadcrumb, BreadcrumbItem, BreadcrumbList, BreadcrumbPage, BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuRadioGroup, DropdownMenuRadioItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useEvents, useModel } from "@/hooks/use-org";
import { LOCALES } from "@/i18n/provider";
import { authApi } from "@/lib/api/endpoints";
import { activeNav, groupOf, moduleOf } from "@/lib/nav";
import { cn } from "@/lib/utils";
import { useAuth } from "@/stores/auth";
import { useUI, type Locale } from "@/stores/ui";

const DATE_LOCALES = { uz, ru, en: enUS } as const;
const SEEN_KEY = "ra-seen-event";

function CompanySelector() {
  const t = useTranslations("top");
  const model = useModel();
  const scope = useUI((s) => s.scope);
  const setScope = useUI((s) => s.setScope);
  const current = scope ? model.dept.get(scope) : undefined;
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex h-10 shrink-0 items-center gap-2.5 whitespace-nowrap rounded-xl border bg-card px-2 pr-3 text-left hover:border-primary/40">
          <span className="grid size-7 place-items-center rounded-lg bg-gradient-to-br from-primary to-violet text-[11px] font-bold text-white">
            {model.state.meta.company.slice(0, 2).toUpperCase()}
          </span>
          <span className="hidden leading-tight md:block">
            <span className="block text-[13px] font-semibold">{model.state.meta.company}</span>
            <span className="block text-[11px] text-muted-foreground">{current?.name ?? t("wholeCompany")}</span>
          </span>
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="start" className="w-64">
        <DropdownMenuLabel>{t("scope")}</DropdownMenuLabel>
        <DropdownMenuRadioGroup value={String(scope ?? "")} onValueChange={(v) => setScope(v ? Number(v) : null)}>
          <DropdownMenuRadioItem value="">
            <Building2 className="size-4" />{t("wholeCompany")}
            <span className="ml-auto text-xs text-muted-foreground">{model.state.members.length}</span>
          </DropdownMenuRadioItem>
          <DropdownMenuSeparator />
          {model.state.departments.map((d) => (
            <DropdownMenuRadioItem key={d.id} value={String(d.id)}>
              <Layers className="size-4" />{d.name}
              <span className="ml-auto text-xs text-muted-foreground">{model.membersOf(d.id).length}</span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function Crumbs({ withModel = true }: { withModel?: boolean }) {
  const t = useTranslations("nav");
  const pathname = usePathname();
  const item = activeNav(pathname);
  const found = groupOf(item);
  const mod = found?.module ?? moduleOf(pathname);
  return (
    <Breadcrumb className="hidden min-w-0 xl:block">
      <BreadcrumbList className="flex-nowrap whitespace-nowrap">
        <BreadcrumbItem className="font-medium text-foreground/80">{t(`modules.${mod.key}`)}</BreadcrumbItem>
        {found && <><BreadcrumbSeparator /><BreadcrumbItem className="text-muted-foreground">{t(`groups.${found.group.key}`)}</BreadcrumbItem></>}
        {item && (
          <>
            <BreadcrumbSeparator />
            {withModel ? <EmployeeCrumb href={item.href} label={t(item.key)} /> : <BreadcrumbItem><BreadcrumbPage>{t(item.key)}</BreadcrumbPage></BreadcrumbItem>}
          </>
        )}
      </BreadcrumbList>
    </Breadcrumb>
  );
}

function EmployeeCrumb({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const model = useModel();
  const employeeId = pathname.match(/^\/employees\/(\d+)/)?.[1];
  const employee = employeeId ? model.member.get(Number(employeeId)) : undefined;
  return (
    <>
      <BreadcrumbItem>{employee ? <Link href={href}>{label}</Link> : <BreadcrumbPage>{label}</BreadcrumbPage>}</BreadcrumbItem>
      {employee && (
        <>
          <BreadcrumbSeparator />
          <BreadcrumbItem><BreadcrumbPage>{employee.name}</BreadcrumbPage></BreadcrumbItem>
        </>
      )}
    </>
  );
}

function Notifications() {
  const t = useTranslations();
  const locale = useLocale() as Locale;
  const model = useModel();
  const events = useEvents(15);
  const [seen, setSeen] = useState(() => Number(localStorage.getItem(SEEN_KEY) ?? 0));
  const list = events.data ?? [];
  const unread = list.filter((e) => e.id > seen).length;
  const pending = model.state.meta.pending_approvals;
  const markSeen = (open: boolean) => {
    if (open && list[0]) {
      localStorage.setItem(SEEN_KEY, String(list[0].id));
      setSeen(list[0].id);
    }
  };
  return (
    <Popover onOpenChange={markSeen}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="relative" aria-label={t("top.notifications")}>
          <Bell className="size-4" />
          {(unread > 0 || pending > 0) && (
            <span className="absolute -right-1.5 -top-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-primary px-1 font-mono text-[10px] text-white ring-2 ring-background">
              {Math.min(99, unread + pending)}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        <div className="flex items-center border-b px-4 py-3 text-sm font-semibold">{t("top.notifications")}</div>
        <div className="max-h-[60vh] overflow-y-auto p-2">
          {pending > 0 && (
            <Link href="/approvals" className="mb-1 flex items-center gap-3 rounded-lg bg-primary/10 px-3 py-2.5 text-sm hover:bg-primary/15">
              <Check className="size-4 text-primary" />{t("top.pendingApprovals", { count: pending })}
            </Link>
          )}
          {model.issueProcesses.length > 0 && (
            <Link href="/gaps" className="mb-1 flex items-center gap-3 rounded-lg bg-warning/10 px-3 py-2.5 text-sm hover:bg-warning/15">
              <span className="size-2 rounded-full bg-warning" />{t("top.attention", { count: model.issueProcesses.length })}
            </Link>
          )}
          <div className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t("top.recent")}</div>
          {list.length === 0 && <p className="px-3 py-4 text-sm text-muted-foreground">{t("top.noNotifications")}</p>}
          {list.map((e) => (
            <div key={e.id} className={cn("rounded-lg px-3 py-2 text-sm", e.id > seen && "bg-muted")}>
              <div className="truncate font-medium">{e.subject || e.to_name || e.from_name}</div>
              <div className="truncate text-xs text-muted-foreground">
                {[e.text || (e.from_name && e.to_name ? `${e.from_name} → ${e.to_name}` : ""), e.actor].filter(Boolean).join(" · ")}
                {" · "}{formatDistanceToNow(new Date(e.at), { addSuffix: true, locale: DATE_LOCALES[locale] })}
              </div>
            </div>
          ))}
        </div>
        <div className="border-t p-2"><Button asChild variant="ghost" size="sm" className="w-full"><Link href="/audit">{t("top.viewAll")}</Link></Button></div>
      </PopoverContent>
    </Popover>
  );
}

export function ThemeSwitcher() {
  const t = useTranslations("top");
  const { theme, setTheme } = useTheme();
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="icon" aria-label={t("theme")}>
          <Sun className="size-4 dark:hidden" />
          <Moon className="hidden size-4 dark:block" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={theme ?? "system"} onValueChange={setTheme}>
          <DropdownMenuRadioItem value="light"><Sun className="size-4" />{t("light")}</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="dark"><Moon className="size-4" />{t("dark")}</DropdownMenuRadioItem>
          <DropdownMenuRadioItem value="system"><Monitor className="size-4" />{t("system")}</DropdownMenuRadioItem>
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

export function LanguageSwitcher() {
  const t = useTranslations("top");
  const locale = useUI((s) => s.locale);
  const setLocale = useUI((s) => s.setLocale);
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="gap-1.5 uppercase" aria-label={t("language")}>
          <Languages className="size-4" />{locale}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuRadioGroup value={locale} onValueChange={(v) => setLocale(v as Locale)}>
          {LOCALES.map((l) => <DropdownMenuRadioItem key={l.code} value={l.code}>{l.label}</DropdownMenuRadioItem>)}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

function UserMenu() {
  const t = useTranslations();
  const model = useModel();
  const router = useRouter();
  const qc = useQueryClient();
  const me = model.state.me;
  if (me.anonymous) return <Button asChild size="sm"><Link href="/login">{t("login.submit")}</Link></Button>;
  const logout = async () => {
    const refresh = useAuth.getState().refresh;
    if (refresh) await authApi.logout(refresh).catch(() => undefined);
    useAuth.getState().logout();
    qc.clear();
    router.replace("/login");
  };
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="flex h-10 items-center gap-2 rounded-xl px-1.5 hover:bg-muted">
          <MemberAvatar name={me.full_name} size={30} />
          <span className="hidden text-left leading-tight lg:block">
            <span className="block max-w-36 truncate text-[13px] font-medium">{me.full_name}</span>
            <span className="block text-[11px] text-muted-foreground">{t(`appRoles.${me.role}`)}</span>
          </span>
          <ChevronDown className="size-3.5 text-muted-foreground" />
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-60">
        <DropdownMenuLabel className="font-normal">
          <div className="font-medium">{me.full_name}</div>
          <div className="text-xs text-muted-foreground">{me.username} · {t(`appRoles.${me.role}`)}</div>
        </DropdownMenuLabel>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild><Link href="/settings?tab=profile"><User className="size-4" />{t("top.profile")}</Link></DropdownMenuItem>
        {me.member && <DropdownMenuItem asChild><Link href={`/employees/${me.member}`}><Orbit className="size-4" />{t("top.my360")}</Link></DropdownMenuItem>}
        <DropdownMenuItem asChild><Link href="/settings"><Settings className="size-4" />{t("nav.settings")}</Link></DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem onSelect={logout} className="text-destructive focus:text-destructive"><LogOut className="size-4" />{t("top.logout")}</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}

/** Yuqori panel: breadcrumb, kompaniya doirasi, qidiruv (Ctrl+K), jonli holat, bildirishnomalar, mavzu, til, profil. */
export function Topbar({ live }: { live: "live" | "connecting" | "offline" }) {
  const t = useTranslations("top");
  const model = useModel();
  const pathname = usePathname();
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [taskOpen, setTaskOpen] = useState(false);
  return (
    <header className="glass relative z-30 flex h-16 shrink-0 items-center gap-2.5 border-b px-4 lg:px-5">
      <CompanySelector />
      <Crumbs />
      <div className="flex-1" />
      <button
        onClick={() => setPaletteOpen(true)}
        className="flex h-9 w-full max-w-sm items-center gap-2 rounded-lg border bg-card px-3 text-sm text-muted-foreground hover:border-primary/40"
      >
        <Search className="size-4" />
        <span className="truncate">{t("searchPlaceholder")}</span>
        <kbd className="ml-auto rounded border px-1.5 font-mono text-[10px]">Ctrl K</kbd>
      </button>
      <span
        title={t(`status.${live}`)}
        className={cn(
          "hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] md:flex",
          live === "live" ? "text-success" : live === "connecting" ? "text-muted-foreground" : "text-warning",
        )}
      >
        <span className={cn("size-1.5 rounded-full", live === "live" ? "bg-success shadow-[0_0_8px_var(--success)]" : live === "connecting" ? "bg-muted-foreground" : "bg-warning")} />
        {t(`status.${live}`)}
      </span>
      {moduleOf(pathname).key === "qrdrive" && <QrBell />}
      <Notifications />
      <ThemeSwitcher />
      <LanguageSwitcher />
      {model.state.me.can.edit && (
        <Button onClick={() => setTaskOpen(true)} className="hidden sm:inline-flex"><Plus className="size-4" />{t("newTask")}</Button>
      )}
      <UserMenu />
      <CommandPalette open={paletteOpen} onOpenChange={setPaletteOpen} />
      <TaskDialog open={taskOpen} onOpenChange={setTaskOpen} />
    </header>
  );
}

/** Zona backendi javob bermaganda: QR Drive sahifalari uchun soddalashtirilgan yuqori panel. */
export function MiniTopbar() {
  const t = useTranslations();
  const router = useRouter();
  const qc = useQueryClient();
  const logout = () => {
    useAuth.getState().logout();
    qc.clear();
    router.replace("/login");
  };
  return (
    <header className="glass relative z-30 flex h-16 shrink-0 items-center gap-2.5 border-b px-4 lg:px-5">
      <Crumbs withModel={false} />
      <div className="flex-1" />
      <QrBell />
      <ThemeSwitcher />
      <LanguageSwitcher />
      <Button variant="ghost" size="sm" onClick={logout}><LogOut className="size-4" />{t("top.logout")}</Button>
    </header>
  );
}
