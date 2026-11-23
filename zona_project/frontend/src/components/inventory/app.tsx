"use client";
/* eslint-disable react/no-unescaped-entities -- o'zbekcha matnlardagi apostrof (o'z, ma'lumot) */

import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, BarChart3, Building2, CheckCircle2, ClipboardList, History, Laptop, LogOut, Moon, Package, Plus,
  RefreshCw, Search, Settings2, ShieldCheck, Sun, Upload, Users,
} from "lucide-react";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { use, useEffect, useRef, useState, type CSSProperties, type ReactNode } from "react";
import { browser } from "react-dom";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { authApi } from "@/lib/api/endpoints";
import { cn } from "@/lib/utils";
import { useAuth } from "@/stores/auth";

import { BranchesView, CatalogView, ExchangeView, HistoryView, UsersView } from "./admin";
import { AnalyticsView } from "./analytics";
import { inv, type Boot } from "./api";
import { EmployeesView } from "./employees";
import { ItemForm, ItemsView, type ItemFilters } from "./items";
import { Btn, Card, Empty, FlagBadge, Kpi, Progress, SectionTitle, Spinner, ago, useBoot } from "./ui";

type Tab = "home" | "items" | "employees" | "analytics" | "history" | "branches" | "exchange" | "users" | "catalog";
const LEVEL_LABEL = { manager: "Boshqaruvchi (IT)", director: "Rahbar", collector: "Filial xodimi" } as const;

function tabsFor(boot: Boot): { key: Tab; label: string; icon: typeof Laptop }[] {
  const m = boot.me;
  return [
    { key: "home", label: "Menyu", icon: ClipboardList },
    { key: "items", label: "Qurilmalar", icon: Laptop },
    { key: "employees", label: "Xodimlar", icon: Users },
    { key: "analytics", label: m.level === "collector" ? "Natijalar" : "Analitika", icon: BarChart3 },
    { key: "history", label: "Tarix", icon: History },
    ...(m.level !== "collector" ? [{ key: "branches" as Tab, label: "Filiallar", icon: Building2 }] : []),
    { key: "exchange", label: "Import / Eksport", icon: Upload },
    ...(m.can.manage ? [{ key: "users" as Tab, label: "Loginlar", icon: ShieldCheck }, { key: "catalog" as Tab, label: "Katalog", icon: Settings2 }] : []),
  ];
}

/* ------------------------------------------------------------------ bosh menyu */
function MenuTile({ icon, label, tone, onClick, big }: { icon: ReactNode; label: string; tone: string; onClick: () => void; big?: boolean }) {
  return (
    <button onClick={onClick} className={cn("flex flex-col items-start gap-4 rounded-3xl border bg-card p-5 text-left shadow-xs transition-all hover:border-primary/40 active:scale-[0.98]",
      big && "col-span-2")}>
      <span className={cn("grid size-12 place-items-center rounded-2xl", tone)}>{icon}</span>
      <span className="text-[15px] font-bold">{label}</span>
    </button>
  );
}

function CollectorHome({ boot, go, add }: { boot: Boot; go: (t: Tab) => void; add: () => void }) {
  const qc = useQueryClient();
  const stats = useQuery({ queryKey: ["inv", "stats", 30], queryFn: () => inv.stats({ days: 30 }) });
  const s = stats.data;
  const mine = s?.leaderboard.find((u) => u.user_id === boot.me.id);
  const finish = async (id: number, done: boolean) => {
    if (done && !confirm("Filialdagi barcha qurilmalar kiritildimi? «Yakunlandi» deb belgilanadi.")) return;
    try {
      await inv.updateBranch(id, { status: done ? "done" : "active" });
      qc.invalidateQueries({ queryKey: ["inv"] });
      toast.success(done ? "Rahmat! Filial «Yakunlandi» deb belgilandi" : "Filial qayta ochildi");
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };
  return (
    <div className="mx-auto w-full max-w-xl space-y-4 p-4 pb-28">
      <button onClick={add} className="flex w-full items-center gap-4 rounded-3xl bg-indigo-600 p-5 text-left text-white shadow-lg shadow-indigo-600/25 active:scale-[0.98]">
        <span className="grid size-14 place-items-center rounded-2xl bg-white/20"><Plus className="size-8" /></span>
        <span><span className="block text-lg font-bold">Qurilma qo'shish</span><span className="text-sm opacity-90">Rasmga olib, ro'yxatdan tanlang</span></span>
      </button>
      <div className="grid grid-cols-2 gap-3">
        <MenuTile icon={<Laptop className="size-6" />} label="Kiritilganlar" tone="bg-emerald-500/10 text-emerald-600" onClick={() => go("items")} />
        <MenuTile icon={<Users className="size-6" />} label="Xodimlar" tone="bg-amber-500/10 text-amber-600" onClick={() => go("employees")} />
      </div>
      {s?.branches.map((b) => (
        <Card key={b.id}>
          <div className="flex items-center gap-2">
            <Building2 className="size-4 text-muted-foreground" />
            <span className="flex-1 font-bold">{b.name}</span>
            <FlagBadge value={b.flag} />
          </div>
          <div className="mt-3 grid grid-cols-3 gap-2">
            <Kpi label="Jami (dona)" value={b.qty} />
            <Kpi label="Bugun" value={b.today} tone="green" />
            <Kpi label="Xodimlar" value={b.employees} tone="amber" />
          </div>
          {b.coverage !== null && (
            <div className="mt-3">
              <div className="mb-1 flex justify-between text-xs text-muted-foreground"><span>Qurilmasi kiritilgan xodimlar</span><b>{b.employees_with_devices}/{b.employees}</b></div>
              <Progress value={b.coverage} />
            </div>
          )}
          {(b.no_serial > 0 || b.no_employee > 0) && (
            <div className="mt-3 rounded-xl bg-amber-500/8 p-3 text-xs text-amber-800 dark:text-amber-300">
              Tekshiring: {b.no_serial > 0 && <>{b.no_serial} ta qurilmada seriya raqam yo'q. </>}{b.no_employee > 0 && <>{b.no_employee} tasiga xodim biriktirilmagan.</>}
            </div>
          )}
          {boot.me.can.write && (b.status === "done" ? (
            <div className="mt-3 flex items-center gap-2 rounded-xl bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-400">
              <CheckCircle2 className="size-5" /><span className="flex-1 font-semibold">Yakunlandi</span>
              <Btn variant="ghost" size="sm" onClick={() => finish(b.id, false)}>Qayta ochish</Btn>
            </div>
          ) : (
            <Btn variant="success" className="mt-3 w-full" onClick={() => finish(b.id, true)} disabled={!b.rows}>
              <CheckCircle2 className="size-4" />Hammasini kiritdim — yakunlash
            </Btn>
          ))}
        </Card>
      ))}
      {mine && <p className="text-center text-sm text-muted-foreground">Siz jami <b>{mine.create}</b> ta qurilma kiritdingiz, oxirgisi {ago(mine.last_at)}.</p>}
      <Card className="bg-muted/30">
        <SectionTitle>Qanday ishlaydi</SectionTitle>
        <ol className="space-y-2 text-sm">
          <li><b>1.</b> «Qurilma qo'shish» ni bosing.</li>
          <li><b>2.</b> Qurilma turini ro'yxatdan tanlang — seriya raqami qayerdaligi o'zi chiqadi.</li>
          <li><b>3.</b> «Kamera» bilan qurilmani va yorlig'ini suratga oling.</li>
          <li><b>4.</b> Kimda turganini tanlang (yo'q bo'lsa — ismini yozib qo'shing).</li>
          <li><b>5.</b> «Saqlash va yana» — keyingi qurilmaga o'ting. Hammasi tugagach «Yakunlash» ni bosing.</li>
        </ol>
      </Card>
    </div>
  );
}

function ManagerHome({ boot, go, add, openBranch }: { boot: Boot; go: (t: Tab) => void; add: () => void; openBranch: (id: number) => void }) {
  const stats = useQuery({ queryKey: ["inv", "stats", 30], queryFn: () => inv.stats({ days: 30 }) });
  const t = stats.data?.totals;
  const lagging = (stats.data?.branches ?? []).filter((b) => b.flag === "slow" || b.flag === "idle");
  return (
    <div className="mx-auto w-full max-w-3xl space-y-4 p-4 pb-28">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        {boot.me.can.write && <MenuTile icon={<Plus className="size-6" />} label="Yangi qurilma" tone="bg-indigo-500/10 text-indigo-600" onClick={add} />}
        <MenuTile icon={<Laptop className="size-6" />} label="Qurilmalar" tone="bg-emerald-500/10 text-emerald-600" onClick={() => go("items")} />
        <MenuTile icon={<Users className="size-6" />} label="Xodimlar" tone="bg-amber-500/10 text-amber-600" onClick={() => go("employees")} />
        <MenuTile icon={<BarChart3 className="size-6" />} label="Analitika" tone="bg-violet-500/10 text-violet-600" onClick={() => go("analytics")} />
        <MenuTile icon={<Building2 className="size-6" />} label="Filiallar" tone="bg-sky-500/10 text-sky-600" onClick={() => go("branches")} />
        <MenuTile icon={<Upload className="size-6" />} label="Import / Eksport" tone="bg-rose-500/10 text-rose-600" onClick={() => go("exchange")} />
        {boot.me.can.manage && <MenuTile icon={<ShieldCheck className="size-6" />} label="Loginlar" tone="bg-teal-500/10 text-teal-600" onClick={() => go("users")} />}
        <MenuTile icon={<History className="size-6" />} label="Tarix" tone="bg-zinc-500/10 text-zinc-600" onClick={() => go("history")} />
        {boot.me.can.manage && <MenuTile icon={<Settings2 className="size-6" />} label="Katalog" tone="bg-orange-500/10 text-orange-600" onClick={() => go("catalog")} />}
      </div>
      <Card>
        <SectionTitle icon={<Package className="size-4" />}>Tizim xulosasi</SectionTitle>
        {!t ? <Spinner className="py-6" /> : (
          <div className="grid grid-cols-2 gap-2.5">
            <Kpi label="Jami qurilmalar (dona)" value={t.qty} onClick={() => go("items")} />
            <Kpi label="Bugun kiritildi" value={t.today} tone="green" />
            <Kpi label="Yakunlangan filiallar" value={`${t.done}/${t.branches}`} tone="amber" onClick={() => go("analytics")} />
            <Kpi label="Xodimlar" value={t.employees_total} tone="violet" onClick={() => go("employees")} />
          </div>
        )}
      </Card>
      {!!lagging.length && (
        <Card>
          <SectionTitle>Sust filiallar</SectionTitle>
          <div className="space-y-1.5">
            {lagging.map((b) => (
              <button key={b.id} onClick={() => openBranch(b.id)} className="flex w-full items-center gap-2 rounded-xl px-2 py-2 text-left hover:bg-muted">
                <span className="flex-1 font-medium">{b.name}</span><span className="text-xs text-muted-foreground">{ago(b.last_at)}</span><FlagBadge value={b.flag} />
              </button>
            ))}
          </div>
        </Card>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ ilova */
function App() {
  const router = useRouter();
  const qc = useQueryClient();
  const boot = useBoot();
  const refresh = useAuth((s) => s.refresh);
  const logoutStore = useAuth((s) => s.logout);
  const { resolvedTheme, setTheme } = useTheme();
  const [tab, setTabState] = useState<Tab>(() => {
    try { return (sessionStorage.getItem("inv-tab") as Tab) || "home"; } catch { return "home"; }
  });
  const [itemFilters, setItemFilters] = useState<ItemFilters | undefined>();
  const [adding, setAdding] = useState(false);
  const [openItemId, setOpenItemId] = useState<number | null>(null);
  const openItem = useQuery({ queryKey: ["inv", "item", openItemId], queryFn: () => inv.item(openItemId!), enabled: !!openItemId });
  const stats = useQuery({ queryKey: ["inv", "stats", 30], queryFn: () => inv.stats({ days: 30 }), enabled: !!boot.data });

  const restricted = boot.data?.me.restricted;
  // platforma foydalanuvchisi kompyuterda kirsa — odatiy (chap menyuli) ko'rinish; ?mobile=1 — mobil ko'rinishda qolish
  useEffect(() => {
    if (restricted !== false) return;
    const stay = new URLSearchParams(window.location.search).get("mobile") === "1";
    if (!stay && window.matchMedia("(min-width: 1024px)").matches) router.replace("/inv");
  }, [restricted, router]);
  // sarlavha balandligi: ro'yxatlarning yopishqoq qidiruv qatori uning ostida turadi
  const headerRef = useRef<HTMLElement>(null);
  const [headerH, setHeaderH] = useState(0);
  useEffect(() => {
    const el = headerRef.current;
    if (!el) return;
    const ro = new ResizeObserver(() => setHeaderH(el.offsetHeight));
    ro.observe(el);
    return () => ro.disconnect();
  }, [boot.data]);
  useEffect(() => {
    // filial xodimlari uchun birinchi kirishda kunduzgi (yorug') rejim — telefonda o'qish oson
    if (!restricted) return;
    try {
      if (!localStorage.getItem("inv-theme-set")) {
        setTheme("light");
        localStorage.setItem("inv-theme-set", "1");
      }
    } catch { /* ruxsat yo'q */ }
  }, [restricted, setTheme]);

  const setTab = (t: Tab) => {
    setTabState(t);
    try { sessionStorage.setItem("inv-tab", t); } catch { /* yo'q */ }
    document.getElementById("inv-scroll")?.scrollTo({ top: 0 });
  };
  const openBranch = (id: number, extra?: Record<string, boolean | string>) => {
    setItemFilters({ branch: String(id), ...extra });
    setTab("items");
  };
  const logout = async () => {
    try { if (refresh) await authApi.logout(refresh); } catch { /* baribir chiqamiz */ }
    logoutStore();
    qc.clear();
    router.replace("/login");
  };

  if (boot.isLoading) return <div className="grid h-full place-items-center"><Spinner /></div>;
  if (boot.isError || !boot.data) {
    return (
      <div className="grid h-full place-items-center p-6">
        <Empty icon={<ShieldCheck className="size-6" />} title="Inventarizatsiya moduliga ruxsat yo'q"
          hint={`${errorMessage(boot.error)} Administratorga murojaat qiling.`}
          action={<div className="flex gap-2"><Btn variant="outline" onClick={() => router.push("/")}>Platformaga</Btn><Btn variant="ghost" onClick={logout}>Chiqish</Btn></div>} />
      </div>
    );
  }
  const b = boot.data;
  const me = b.me;
  const tabs = tabsFor(b);
  const current = tabs.some((x) => x.key === tab) ? tab : "home";
  const counts: Partial<Record<Tab, string>> = stats.data ? {
    items: `${stats.data.totals.rows}`, employees: `${stats.data.totals.employees_total}`,
  } : {};
  const initials = me.name.split(/\s+/).slice(0, 2).map((w) => w[0]).join("").toUpperCase() || "U";
  const subtitle = me.level === "collector" ? b.branches.map((x) => x.name).join(", ") || LEVEL_LABEL[me.level] : LEVEL_LABEL[me.level];

  return (
    <div id="inv-scroll" className="h-full overflow-y-auto bg-background" style={{ "--inv-top": `${headerH}px` } as CSSProperties}>
      <header ref={headerRef} className="sticky top-0 z-30 border-b bg-background/90 backdrop-blur supports-[backdrop-filter]:bg-background/75">
        <div className="mx-auto flex max-w-7xl items-center gap-3 px-3 pb-2 pt-3 sm:px-4">
          {!me.restricted && (
            <button onClick={() => router.push("/inv")} className="grid size-10 shrink-0 place-items-center rounded-xl hover:bg-muted" title="Odatiy (kompyuter) ko'rinish"><ArrowLeft className="size-5" /></button>
          )}
          <span className="grid size-10 shrink-0 place-items-center rounded-xl bg-indigo-600 text-sm font-bold text-white">{initials}</span>
          <div className="min-w-0 flex-1 leading-tight">
            <div className="truncate font-bold">{me.name}</div>
            <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
          </div>
          <button onClick={() => { setItemFilters({}); setTab("items"); }} className="grid size-10 place-items-center rounded-xl bg-indigo-500/10 text-indigo-600" title="Qidirish"><Search className="size-5" /></button>
          <button onClick={() => { qc.invalidateQueries({ queryKey: ["inv"] }); toast.success("Yangilandi"); }} className="hidden size-10 place-items-center rounded-xl hover:bg-muted sm:grid" title="Yangilash"><RefreshCw className="size-5" /></button>
          <button onClick={() => setTheme(resolvedTheme === "dark" ? "light" : "dark")} className="grid size-10 place-items-center rounded-xl hover:bg-muted" title="Kun / tun">
            {resolvedTheme === "dark" ? <Sun className="size-5" /> : <Moon className="size-5" />}
          </button>
          <button onClick={logout} className="grid size-10 place-items-center rounded-xl hover:bg-muted" title="Chiqish"><LogOut className="size-5" /></button>
        </div>
        <nav className="mx-auto flex max-w-7xl gap-1.5 overflow-x-auto px-3 pb-2.5 [scrollbar-width:none] sm:px-4">
          {tabs.map((x) => (
            <button key={x.key} onClick={() => { if (x.key === "items") setItemFilters(undefined); setTab(x.key); }}
              className={cn("flex h-10 shrink-0 items-center gap-2 rounded-xl px-3.5 text-sm font-semibold transition-colors",
                current === x.key ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/25" : "text-muted-foreground hover:bg-muted hover:text-foreground")}>
              <x.icon className="size-4" />{x.label}{counts[x.key] && <span className="opacity-75">({counts[x.key]})</span>}
            </button>
          ))}
        </nav>
      </header>

      <main>
        {current === "home" && (me.level === "collector"
          ? <CollectorHome boot={b} go={setTab} add={() => setAdding(true)} />
          : <ManagerHome boot={b} go={setTab} add={() => setAdding(true)} openBranch={openBranch} />)}
        {current === "items" && <ItemsView key={JSON.stringify(itemFilters ?? null)} initial={itemFilters} onAdd={() => setAdding(true)} />}
        {current === "employees" && <EmployeesView onShowItems={(id) => { setItemFilters({ employee: String(id) }); setTab("items"); }} />}
        {current === "analytics" && <AnalyticsView onOpenBranch={openBranch} />}
        {current === "history" && <HistoryView onOpenItem={setOpenItemId} />}
        {current === "branches" && <BranchesView onOpen={openBranch} />}
        {current === "exchange" && <ExchangeView />}
        {current === "users" && <UsersView />}
        {current === "catalog" && <CatalogView />}
      </main>

      {me.can.write && (current === "items" || current === "home") && (
        <button onClick={() => setAdding(true)} aria-label="Qurilma qo'shish"
          className="fixed bottom-[max(1.25rem,env(safe-area-inset-bottom))] right-5 z-30 grid size-16 place-items-center rounded-full bg-indigo-600 text-white shadow-xl shadow-indigo-600/30 active:scale-95 sm:hidden">
          <Plus className="size-8" />
        </button>
      )}
      <ItemForm open={adding} onClose={() => setAdding(false)} />
      <ItemForm open={!!openItemId && !!openItem.data} item={openItem.data ?? null} onClose={() => setOpenItemId(null)} />
    </div>
  );
}

/** /inventory — mustaqil yengil sahifa (platforma menyusisiz): filial xodimlari faqat shu yerni ko'radi. */
export function InventoryRoot() {
  use(browser("JWT tokenlar localStorage'da saqlanadi"));
  const router = useRouter();
  const access = useAuth((s) => s.access);
  const refresh = useAuth((s) => s.refresh);
  useEffect(() => {
    if (!access && !refresh) router.replace("/login?next=/inventory");
  }, [access, refresh, router]);
  if (!access && !refresh) return <div className="grid h-full place-items-center"><Spinner /></div>;
  return <App />;
}
