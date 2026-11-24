"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Building2, FileSignature, FileSpreadsheet, History, KeyRound, Laptop, Plus, Settings2, ShieldCheck, Smartphone, Users } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { AcksView } from "./acks";
import { BranchesView, CatalogView, ExchangeView, HistoryView, UsersView } from "./admin";
import { AnalyticsView } from "./analytics";
import { download, inv } from "./api";
import { LangToggle } from "./app";
import { EmployeesView } from "./employees";
import { useT } from "./i18n";
import { ItemForm, ItemsView, type ItemFilters } from "./items";
import { Empty, Spinner, useBoot } from "./ui";

export type DesktopView = "overview" | "items" | "employees" | "acks" | "branches" | "history" | "exchange" | "users" | "catalog";

const META: Record<DesktopView, { title: string; description: string; icon: typeof Laptop }> = {
  overview: { title: "Inventarizatsiya natijalari", description: "Filiallar holati, sust filiallar, kunlik faollik va kim qancha ish qilgani — rahbarlarga ko'rsatish uchun", icon: BarChart3 },
  items: { title: "Qurilmalar", description: "Filiallardan kiritilgan barcha qurilmalar: rasm, seriya raqami, holati va kimda turgani", icon: Laptop },
  employees: { title: "Xodimlar", description: "Filial, tashkilot (loyiha) va bo'lim bo'yicha xodimlar; import / eksport va shablon", icon: Users },
  acks: { title: "Tasdiqnomalar", description: "Xodimlarga havola yuborish va ularning imzosi: kim tasdiqladi, kim kutilmoqda, kimda e'tiroz bor", icon: FileSignature },
  branches: { title: "Filiallar", description: "Har bir filialning inventarizatsiya holati, o'tkazuvchisi va loginlari", icon: Building2 },
  history: { title: "Tarix", description: "Kim, qachon, qaysi filialda nima qo'shdi, o'zgartirdi yoki o'chirdi", icon: History },
  exchange: { title: "Import / Eksport", description: "CSV, Excel va asl shablon formatida yuklab olish; to'ldirilgan fayldan yuklash", icon: FileSpreadsheet },
  users: { title: "Loginlar va huquqlar", description: "Filial loginlari, rahbarlar va boshqaruvchilar; loginlar fayli", icon: ShieldCheck },
  catalog: { title: "Katalog", description: "Qurilma turlari va brendlar, tashkilotlar, joylar", icon: Settings2 },
};

function filtersFrom(params: URLSearchParams): ItemFilters | undefined {
  const f: ItemFilters = {};
  for (const k of ["q", "branch", "org", "type", "condition", "group", "employee"] as const) {
    const v = params.get(k);
    if (v) f[k] = v;
  }
  for (const k of ["no_serial", "no_employee", "no_photo", "mine", "deleted"] as const) {
    if (params.get(k) === "1") f[k] = true;
  }
  return Object.keys(f).length ? f : undefined;
}

function toQuery(f: Record<string, string | boolean | undefined>) {
  const q = new URLSearchParams();
  Object.entries(f).forEach(([k, v]) => v && q.set(k, v === true ? "1" : String(v)));
  const s = q.toString();
  return s ? `?${s}` : "";
}

/** Platforma ichidagi (chap menyu + yuqori panel) inventarizatsiya sahifasi — kompyuterda ishlash uchun. */
export function InvDesktop({ view }: { view: DesktopView }) {
  const router = useRouter();
  const t = useT();
  const params = useSearchParams();
  const boot = useBoot();
  const [adding, setAdding] = useState(false);
  const [openItemId, setOpenItemId] = useState<number | null>(null);
  const openItem = useQuery({ queryKey: ["inv", "item", openItemId], queryFn: () => inv.item(openItemId!), enabled: !!openItemId });
  const initial = useMemo(() => filtersFrom(new URLSearchParams(params.toString())), [params]);
  const meta = META[view];
  const Icon = meta.icon;

  const openBranch = (id: number, extra?: Record<string, boolean | string>) => router.push(`/inv/items${toQuery({ branch: String(id), ...extra })}`);

  if (boot.isLoading) return <Spinner />;
  if (boot.isError || !boot.data) {
    return <div className="p-8"><Empty icon={<ShieldCheck className="size-6" />} title={t("Inventarizatsiya moduliga ruxsat yo'q")} hint={errorMessage(boot.error)} /></div>;
  }
  const me = boot.data.me;
  if ((view === "users" || view === "catalog") && !me.can.manage) {
    return <div className="p-8"><Empty icon={<KeyRound className="size-6" />} title={t("Bu bo'lim faqat boshqaruvchi uchun")} /></div>;
  }

  let actions: ReactNode = null;
  if (view === "overview" || view === "items") {
    actions = (
      <>
        {view === "items" && (
          <Button variant="outline" size="sm" onClick={() => download("items/export/", { ...initial, fmt: "template" }).catch((e) => toast.error(errorMessage(e)))}>
            <FileSpreadsheet className="size-4" />{t("Shablon formatida")}
          </Button>
        )}
        {me.can.write && <Button size="sm" onClick={() => setAdding(true)}><Plus className="size-4" />{t("Qurilma qo'shish")}</Button>}
      </>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <header className="shrink-0 border-b bg-background/85 backdrop-blur supports-[backdrop-filter]:bg-background/70">
        <div className="mx-auto flex w-full max-w-[1800px] flex-wrap items-center gap-x-3 gap-y-1.5 px-4 py-2 sm:px-5">
          <span className="grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Icon className="size-4" /></span>
          <div className="flex min-w-0 flex-1 items-baseline gap-2">
            <h1 className="shrink-0 text-[15px] font-semibold leading-tight tracking-tight">{t(meta.title)}</h1>
            <p className="hidden truncate text-xs text-muted-foreground lg:block" title={t(meta.description)}>{t(meta.description)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {actions}
            <LangToggle className="h-8 min-w-8 rounded-lg" />
            <Button variant="ghost" size="icon-sm" title={t("Mobil ko'rinish (filial xodimlari ko'radigan)")} asChild>
              <Link href="/inventory?mobile=1"><Smartphone className="size-4" /></Link>
            </Button>
          </div>
        </div>
      </header>
      <div className={cn("min-h-0 flex-1 overflow-y-auto", view === "overview" && "px-3 py-3 sm:px-5")}>
        {view === "overview" && <AnalyticsView embedded onOpenBranch={openBranch} />}
        {view === "items" && <ItemsView key={params.toString()} table initial={initial} onAdd={() => setAdding(true)} />}
        {view === "employees" && <EmployeesView table onShowItems={(id) => router.push(`/inv/items?employee=${id}`)} />}
        {view === "acks" && <AcksView table />}
        {view === "branches" && <BranchesView onOpen={(id) => openBranch(id)} />}
        {view === "history" && <HistoryView onOpenItem={setOpenItemId} />}
        {view === "exchange" && <ExchangeView />}
        {view === "users" && <UsersView />}
        {view === "catalog" && <CatalogView />}
      </div>
      <ItemForm open={adding} onClose={() => setAdding(false)} />
      <ItemForm open={!!openItemId && !!openItem.data} item={openItem.data ?? null} onClose={() => setOpenItemId(null)} />
    </div>
  );
}
