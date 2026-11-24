"use client";

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, AtSign, BatteryCharging, CalendarClock, Camera, Download, History, ImageOff, ImagePlus, Info, Keyboard, Loader2,
  MapPin, Minus, Monitor, Package, Phone, Plus, Printer, Projector, RotateCcw, Router, ScanBarcode, ShieldCheck,
  Smartphone, Trash2, User, Wallet, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { download, inv, type Boot, type Condition, type Employee, type Item, type ItemInput, type Params, type PhotoRef } from "./api";
import { condLabel, loc, tr, useLang, useT, type Lang } from "./i18n";
import {
  Btn, COND_STYLE, CondBadge, Empty, Field, FilterBar, Overlay, Picker, Spinner, ToggleChip, ago, compressImage, dt, inputCls,
  useBoot, type FilterChip, type Opt,
} from "./ui";

/* ------------------------------------------------------------------ yordamchilar */
const GROUP_ICON: Record<string, typeof Monitor> = {
  Kompyuter: Monitor, Periferiya: Keyboard, Printer, Tarmoq: Router, Elektr: BatteryCharging, Xavfsizlik: ShieldCheck,
  Aloqa: Smartphone, Savdo: ScanBarcode, Multimedia: Projector,
};
export function GroupIcon({ group, className }: { group: string; className?: string }) {
  const Icon = GROUP_ICON[group] ?? Package;
  return <Icon className={className} />;
}

/** Qurilma turi va joy nomlari tanlangan tilda (katalogdan). */
export function useCatalogNames() {
  const boot = useBoot().data;
  const lang = useLang();
  return useMemo(() => {
    const types = new Map((boot?.device_types ?? []).map((d) => [d.id, d]));
    const places = new Map((boot?.locations ?? []).map((l) => [l.name, l]));
    return {
      lang,
      type: (id: number, fallback = "") => loc(types.get(id), "name", lang) || fallback,
      place: (name: string) => (name ? loc(places.get(name), "name", lang) || name : ""),
      group: (g: string) => tr(g, undefined, lang),
    };
  }, [boot, lang]);
}

export function useEmployees(branch: number | null | undefined) {
  return useQuery({
    queryKey: ["inv", "employees", "branch", branch ?? 0],
    queryFn: () => inv.employees({ branch: branch ?? undefined, limit: 5000 }),
    staleTime: 60_000,
    enabled: branch !== undefined,
  });
}

/** Sanaga oy qo'shish (backend bilan bir xil: 31-yanvar + 1 oy = fevral oxiri). */
export function addMonths(iso: string | null | undefined, months: number | null | undefined): string | null {
  if (!iso || !months) return null;
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return null;
  const total = m - 1 + months;
  const year = y + Math.floor(total / 12), month = (total % 12) + 1;
  const day = Math.min(d, new Date(year, month, 0).getDate());
  return `${year}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}
export const money = (n: number | null | undefined) => (n || n === 0 ? n.toLocaleString("ru-RU").replace(/\u00a0/g, " ") : "");
export const dmy = (iso: string | null | undefined) => (iso ? iso.slice(0, 10).split("-").reverse().join(".") : "");
export type WarrantyState = "expired" | "soon" | "active" | "none";
export function warrantyState(until: string | null | undefined): WarrantyState {
  if (!until) return "none";
  const today = new Date().toISOString().slice(0, 10);
  const soon = new Date(Date.now() + 90 * 86400_000).toISOString().slice(0, 10);
  return until < today ? "expired" : until <= soon ? "soon" : "active";
}
export const WARRANTY_STYLE: Record<WarrantyState, string> = {
  expired: "text-red-600", soon: "text-amber-600", active: "text-emerald-600", none: "text-muted-foreground",
};

const LAST_KEY = "inv-last";
const DRAFT_KEY = "inv-draft";
function readLast(): Partial<ItemInput> {
  try {
    return JSON.parse(localStorage.getItem(LAST_KEY) || "{}");
  } catch {
    return {};
  }
}

function emptyForm(boot: Boot, preset?: Partial<ItemInput>): ItemInput {
  const last = readLast();
  const myBranches = boot.me.branches;
  const branch = preset?.branch ?? (myBranches?.length === 1 ? myBranches[0] : last.branch ?? null);
  return {
    org: preset?.org ?? last.org ?? null, branch, location: preset?.location ?? last.location ?? "",
    device_type: preset?.device_type ?? null, brand: "", model: "", serial: "", quantity: 1, condition: "ok",
    employee: preset?.employee ?? null, note: "", photos: [], purchase_price: null, purchase_date: "", warranty_months: null,
  };
}

function fromItem(it: Item): ItemInput {
  return {
    org: it.org, branch: it.branch, location: it.location, device_type: it.device_type, brand: it.brand, model: it.model,
    serial: it.serial, quantity: it.quantity, condition: it.condition, employee: it.employee, note: it.note,
    photos: it.photos.map((p) => p.id), purchase_price: it.purchase_price, purchase_date: it.purchase_date ?? "",
    warranty_months: it.warranty_months,
  };
}

const FIELD_LABEL: Record<string, string> = {
  org: "Tashkilot", branch: "Filial", location: "Qayerda turibdi", device_type: "Qurilma turi", brand: "Brend",
  model: "Model", serial: "Seriya raqami", quantity: "Soni", condition: "Holati", employee: "Xodim", note: "Izoh",
  photos: "Rasmlar", purchase_price: "Sotib olingan narxi", purchase_date: "Sotib olingan sana",
  warranty_months: "Kafolat muddati", phone: "Telefon", telegram: "Telegram", full_name: "F.I.Sh.", position: "Lavozimi", status: "Holati",
};
const ACTION_LABEL: Record<string, string> = {
  create: "Qo'shdi", update: "O'zgartirdi", delete: "O'chirdi", restore: "Tikladi", import: "Import", status: "Holat",
  login: "Kirdi", sign: "Imzoladi",
};
export const fieldLabel = (k: string, lang: Lang) => tr(FIELD_LABEL[k] ?? k, undefined, lang);
export const actionLabel = (a: string, lang: Lang) => tr(ACTION_LABEL[a] ?? a, undefined, lang);

/* ------------------------------------------------------------------ rasmlar */
function PhotoBlock({ photos, setPhotos, disabled }: {
  photos: PhotoRef[]; setPhotos: (p: PhotoRef[]) => void; disabled?: boolean;
}) {
  const t = useT();
  const camera = useRef<HTMLInputElement>(null);
  const gallery = useRef<HTMLInputElement>(null);
  const [progress, setProgress] = useState<number | null>(null);
  const [view, setView] = useState<PhotoRef | null>(null);

  const onFiles = async (list: FileList | null) => {
    if (!list?.length) return;
    const files = Array.from(list).slice(0, 12);
    setProgress(0);
    try {
      const ready = await Promise.all(files.map((f) => compressImage(f)));
      const added = await inv.uploadPhotos(ready, setProgress);
      setPhotos([...photos, ...added]);
      toast.success(t("{n} ta rasm qo'shildi", { n: added.length }));
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setProgress(null);
      if (camera.current) camera.current.value = "";
      if (gallery.current) gallery.current.value = "";
    }
  };

  return (
    <div className="rounded-2xl border bg-muted/30 p-3">
      <div className="mb-3 flex items-center gap-2">
        <Camera className="size-4 text-muted-foreground" />
        <span className="flex-1 text-sm font-semibold">{t("Qurilma rasmlari")}</span>
        <span className="font-mono text-xs text-muted-foreground">{t("{n} ta rasm", { n: photos.length })}</span>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        <button type="button" disabled={disabled || progress !== null} onClick={() => camera.current?.click()}
          className="flex aspect-square flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-emerald-500/40 bg-emerald-500/5 text-emerald-700 active:scale-95 dark:text-emerald-400">
          <Camera className="size-6" /><span className="text-xs font-semibold">{t("Kamera")}</span>
        </button>
        <button type="button" disabled={disabled || progress !== null} onClick={() => gallery.current?.click()}
          className="flex aspect-square flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-indigo-500/40 bg-indigo-500/5 text-indigo-700 active:scale-95 dark:text-indigo-400">
          <ImagePlus className="size-6" /><span className="text-xs font-semibold">{t("Galereya")}</span>
        </button>
        {progress !== null && (
          <div className="flex aspect-square flex-col items-center justify-center gap-1 rounded-xl border bg-card text-xs text-muted-foreground">
            <Loader2 className="size-5 animate-spin" />{progress}%
          </div>
        )}
        {photos.map((p) => (
          <div key={p.id} className="relative aspect-square overflow-hidden rounded-xl border bg-card">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={p.thumb} alt="" loading="lazy" className="size-full object-cover" onClick={() => setView(p)} />
            {!disabled && (
              <button type="button" onClick={() => setPhotos(photos.filter((x) => x.id !== p.id))}
                className="absolute right-1 top-1 grid size-7 place-items-center rounded-full bg-black/60 text-white" aria-label={t("Olib tashlash")}>
                <X className="size-4" />
              </button>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">{t("Qurilmaning o'zini va seriya raqami yozilgan yorlig'ini suratga oling. Bir nechta rasm mumkin.")}</p>
      <input ref={camera} type="file" accept="image/*" capture="environment" multiple hidden onChange={(e) => onFiles(e.target.files)} />
      <input ref={gallery} type="file" accept="image/*" multiple hidden onChange={(e) => onFiles(e.target.files)} />
      {view && (
        <div className="fixed inset-0 z-[90] flex items-center justify-center bg-black/90 p-3" onClick={() => setView(null)}>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={view.url} alt="" className="max-h-full max-w-full rounded-lg object-contain" />
          <button className="absolute right-3 top-3 grid size-11 place-items-center rounded-full bg-white/15 text-white"><X className="size-6" /></button>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ holat tugmalari */
function ConditionChips({ value, onChange, options }: {
  value: Condition; onChange: (v: Condition) => void; options: Boot["conditions"];
}) {
  const lang = useLang();
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)}
          className={cn("h-11 rounded-xl border px-3 text-sm font-semibold transition-all md:h-9",
            value === o.value ? cn(COND_STYLE[o.value], "border-current ring-2 ring-current/20") : "bg-card text-muted-foreground")}>
          {condLabel(o.value, lang)}
        </button>
      ))}
    </div>
  );
}

function Stepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="flex h-12 items-center overflow-hidden rounded-xl border bg-card md:h-10">
      <button type="button" onClick={() => onChange(Math.max(1, value - 1))} className="grid h-full w-12 place-items-center hover:bg-muted"><Minus className="size-4" /></button>
      <input inputMode="numeric" value={value} onChange={(e) => onChange(Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1))}
        className="h-full min-w-0 flex-1 bg-transparent text-center text-lg font-semibold tabular-nums outline-none" />
      <button type="button" onClick={() => onChange(value + 1)} className="grid h-full w-12 place-items-center hover:bg-muted"><Plus className="size-4" /></button>
    </div>
  );
}

/* ------------------------------------------------------------------ xodim kontaktlari (tasdiqlash havolasi uchun) */
interface Contact { id: number; phone: string; telegram: string; noTg: boolean }

function ContactBlock({ contact, onChange, invalid, disabled }: {
  contact: Contact; onChange: (c: Contact) => void; invalid: { phone?: boolean; telegram?: boolean }; disabled?: boolean;
}) {
  const t = useT();
  return (
    <div className="space-y-3 rounded-2xl border border-indigo-500/25 bg-indigo-500/[0.04] p-3">
      <div className="text-xs text-muted-foreground">
        {t("Xodimga tasdiqlash havolasi yuboriladi — u qurilmalarni ko'rib, imzo qo'yadi. Telefon va Telegramini yozing.")}
      </div>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <Field label={t("Xodim telefoni")} required>
          <div className={cn("flex items-center gap-2 rounded-xl border bg-card px-3 focus-within:border-primary md:rounded-lg", invalid.phone && "border-destructive ring-2 ring-destructive/15")}>
            <Phone className="size-4 shrink-0 text-muted-foreground" />
            <input className="h-12 min-w-0 flex-1 bg-transparent text-[15px] outline-none md:h-10 md:text-sm" inputMode="tel" disabled={disabled}
              value={contact.phone} onChange={(e) => onChange({ ...contact, phone: e.target.value })} placeholder="+998 90 123 45 67" />
          </div>
        </Field>
        <Field label={t("Telegram username")} required={!contact.noTg}>
          <div className={cn("flex items-center gap-2 rounded-xl border bg-card px-3 focus-within:border-primary md:rounded-lg", contact.noTg && "opacity-50",
            invalid.telegram && "border-destructive ring-2 ring-destructive/15")}>
            <AtSign className="size-4 shrink-0 text-muted-foreground" />
            <input className="h-12 min-w-0 flex-1 bg-transparent text-[15px] outline-none md:h-10 md:text-sm" disabled={disabled || contact.noTg}
              autoCapitalize="none" autoCorrect="off" spellCheck={false}
              value={contact.telegram} onChange={(e) => onChange({ ...contact, telegram: e.target.value.replace(/^@/, "") })} placeholder="username" />
          </div>
        </Field>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" className="size-5" checked={contact.noTg} disabled={disabled}
          onChange={(e) => onChange({ ...contact, noTg: e.target.checked, telegram: e.target.checked ? "" : contact.telegram })} />
        {t("Xodimda Telegram yo'q")}
      </label>
    </div>
  );
}

/* ------------------------------------------------------------------ xarid va kafolat */
function PurchaseBlock({ form, set, disabled }: {
  form: ItemInput; set: <K extends keyof ItemInput>(key: K, value: ItemInput[K]) => void; disabled?: boolean;
}) {
  const t = useT();
  const until = addMonths(form.purchase_date, form.warranty_months);
  const state = warrantyState(until);
  return (
    <div className="rounded-2xl border bg-muted/30 p-3">
      <div className="mb-3 flex items-center gap-2">
        <Wallet className="size-4 text-muted-foreground" />
        <span className="flex-1 text-sm font-semibold">{t("Xarid va kafolat")}</span>
        <span className="text-xs text-muted-foreground">{t("ixtiyoriy")}</span>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label={t("Sotib olingan narxi (so'm)")}>
          <input className={cn(inputCls, "font-mono tabular-nums")} inputMode="numeric" disabled={disabled} placeholder="0"
            value={money(form.purchase_price)}
            onChange={(e) => { const d = e.target.value.replace(/\D/g, "").slice(0, 15); set("purchase_price", d ? Number(d) : null); }} />
        </Field>
        <Field label={t("Kafolat muddati (oy)")}>
          <input className={inputCls} inputMode="numeric" disabled={disabled} placeholder="12"
            value={form.warranty_months ?? ""}
            onChange={(e) => { const d = e.target.value.replace(/\D/g, "").slice(0, 3); set("warranty_months", d ? Math.min(600, Number(d)) : null); }} />
        </Field>
        <Field label={t("Sotib olingan sana")}>
          <input type="date" className={inputCls} disabled={disabled} value={form.purchase_date}
            max={new Date().toISOString().slice(0, 10)} onChange={(e) => set("purchase_date", e.target.value)} />
        </Field>
        <Field label={t("Kafolat tugaydi")}>
          <div className={cn("flex h-12 items-center gap-2 rounded-xl border bg-muted/50 px-3 text-[15px] md:h-10 md:rounded-lg md:text-sm", WARRANTY_STYLE[state])}>
            <CalendarClock className="size-4 shrink-0" />
            <span className="truncate">{until ? dmy(until) : "—"}</span>
          </div>
        </Field>
      </div>
      {until && state !== "active" && (
        <p className={cn("mt-2 text-xs font-medium", WARRANTY_STYLE[state])}>
          {state === "expired" ? t("Kafolat muddati tugagan") : t("Kafolat 90 kun ichida tugaydi")}
        </p>
      )}
      {!until && (form.purchase_date || form.warranty_months) ? (
        <p className="mt-2 text-xs text-muted-foreground">{t("Kafolat tugash sanasi uchun sotib olingan sana va muddatni yozing")}</p>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ qurilma formasi */
type Draft = { form: ItemInput; photos: PhotoRef[] };

function readDraft(): Draft | null {
  try {
    const d = JSON.parse(localStorage.getItem(DRAFT_KEY) || "null") as Draft | null;
    return d?.form?.device_type ? d : null;
  } catch {
    return null;
  }
}

/** Oyna ochilganda forma har safar yangidan (key bilan) o'rnatiladi. */
export function ItemForm({ open, onClose, item, preset }: {
  open: boolean; onClose: () => void; item?: Item | null; preset?: Partial<ItemInput>;
}) {
  const boot = useBoot().data;
  const t = useT();
  if (!open) return null;
  if (!boot) return <Overlay open onClose={onClose} title={t("Qurilma")}><Spinner /></Overlay>;
  return <ItemFormBody key={item?.id ?? "new"} boot={boot} onClose={onClose} item={item} preset={preset} />;
}

function ItemFormBody({ boot, onClose, item, preset }: {
  boot: Boot; onClose: () => void; item?: Item | null; preset?: Partial<ItemInput>;
}) {
  const t = useT();
  const lang = useLang();
  const names = useCatalogNames();
  const qc = useQueryClient();
  // yangi qurilma uchun saqlanmagan qoralama tiklanadi
  const [restored] = useState<Draft | null>(() => (!item && !preset ? readDraft() : null));
  const [form, setForm] = useState<ItemInput>(() => (item ? fromItem(item) : restored?.form ?? emptyForm(boot, preset)));
  const [photos, setPhotos] = useState<PhotoRef[]>(() => (item ? item.photos : restored?.photos ?? []));
  const [saving, setSaving] = useState<"" | "save" | "more">("");
  const [errors, setErrors] = useState<Record<string, boolean>>({});
  const [dup, setDup] = useState<Item["duplicate"]>(null);
  const [confirmDel, setConfirmDel] = useState(false);
  const [contactEdit, setContactEdit] = useState<Contact | null>(null);
  const detail = useQuery({ queryKey: ["inv", "item", item?.id], queryFn: () => inv.item(item!.id), enabled: !!item });
  const isNew = !item;

  useEffect(() => {
    if (restored) toast.info(tr("Saqlanmagan qoralama tiklandi"));
  }, [restored]);

  // qoralama: yangi qurilma formasi har o'zgarganda saqlanadi (sahifa yangilansa yo'qolmaydi)
  useEffect(() => {
    if (!isNew) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ form, photos }));
    } catch { /* joy yo'q */ }
  }, [form, photos, isNew]);

  const employees = useEmployees(form.branch ?? null);
  const type = boot.device_types.find((d) => d.id === form.device_type);

  const typeOpts = useMemo<Opt[]>(() => boot.device_types.filter((d) => d.is_active || d.id === form.device_type)
    .map((d) => ({ value: String(d.id), label: loc(d, "name", lang), hint: loc(d, "description", lang), group: tr(d.group, undefined, lang) })),
  [boot, form.device_type, lang]);
  const brandOpts = useMemo<Opt[]>(() => (type?.brands ?? []).map((b) => ({ value: b, label: b === "Boshqa" ? tr(b, undefined, lang) : b })), [type, lang]);
  const empOpts = useMemo<Opt[]>(() => (employees.data?.results ?? []).map((e) => ({
    value: String(e.id), label: e.full_name, hint: [e.position, e.project, e.phone, e.telegram && `@${e.telegram}`].filter(Boolean).join(" · "),
  })), [employees.data]);
  const branchOpts = useMemo<Opt[]>(() => boot.branches.map((b) => ({ value: String(b.id), label: b.name, hint: b.region })), [boot]);
  const orgOpts = useMemo<Opt[]>(() => boot.orgs.map((o) => ({ value: String(o.id), label: o.name })), [boot]);
  const locOpts = useMemo<Opt[]>(() => boot.locations.map((l) => ({ value: l.name, label: loc(l, "name", lang) })), [boot, lang]);

  const set = <K extends keyof ItemInput>(key: K, value: ItemInput[K]) => {
    setForm((f) => ({ ...f, [key]: value }));
    setErrors((e) => ({ ...e, [key]: false }));
  };
  const canWrite = boot.me.can.write && !item?.is_deleted;
  const fixedBranch = boot.me.branches?.length === 1;
  const emp: Employee | undefined = employees.data?.results.find((e) => e.id === form.employee);
  const contact: Contact | null = emp
    ? (contactEdit?.id === emp.id ? contactEdit : { id: emp.id, phone: emp.phone, telegram: emp.telegram, noTg: false })
    : null;

  const checkSerial = async () => {
    if (form.serial.trim().length < 3) return setDup(null);
    try {
      setDup((await inv.checkSerial(form.serial.trim(), item?.id)).duplicate);
    } catch { /* tekshiruv ixtiyoriy */ }
  };

  const save = async (more: boolean) => {
    const errs: Record<string, boolean> = { device_type: !form.device_type, branch: !form.branch };
    if (contact) {
      errs.phone = !contact.phone.trim();
      errs.telegram = !contact.noTg && !contact.telegram.trim();
    }
    setErrors(errs);
    if (errs.branch) return void toast.error(t("Filialni tanlang"));
    if (errs.device_type) return void toast.error(t("Qurilma turini tanlang"));
    if (errs.phone || errs.telegram) return void toast.error(t("Xodimning telefoni va Telegramini yozing"));
    setSaving(more ? "more" : "save");
    try {
      if (emp && contact && (contact.phone !== emp.phone || contact.telegram !== emp.telegram)) {
        await inv.updateEmployee(emp.id, { phone: contact.phone, telegram: contact.telegram });
      }
      const body = { ...form, photos: photos.map((p) => p.id) };
      const saved = item ? await inv.updateItem(item.id, body) : await inv.createItem(body);
      localStorage.setItem(LAST_KEY, JSON.stringify({ org: form.org, branch: form.branch, location: form.location }));
      if (isNew) localStorage.removeItem(DRAFT_KEY);
      qc.invalidateQueries({ queryKey: ["inv"], predicate: (q) => q.queryKey[1] !== "boot" });
      toast.success(t("{n} saqlandi", { n: saved.inv_number }), {
        description: saved.duplicate
          ? t("Diqqat: bu seriya raqam {n} ({b}) da ham bor", { n: saved.duplicate.inv_number, b: saved.duplicate.branch }) : undefined,
      });
      if (more) {
        setForm({ ...emptyForm(boot), org: form.org, branch: form.branch, location: form.location, employee: form.employee });
        setPhotos([]);
        setDup(null);
        document.getElementById("inv-form-top")?.scrollIntoView({ behavior: "smooth" });
      } else {
        onClose();
      }
    } catch (e) {
      toast.error(errorMessage(e));
    } finally {
      setSaving("");
    }
  };

  const remove = async () => {
    if (!item) return;
    try {
      await inv.deleteItem(item.id);
      qc.invalidateQueries({ queryKey: ["inv"], predicate: (q) => q.queryKey[1] !== "boot" });
      toast.success(t("{n} o'chirildi", { n: item.inv_number }), {
        action: { label: t("Qaytarish"), onClick: () => inv.restoreItem(item.id).then(() => qc.invalidateQueries({ queryKey: ["inv"] })) },
      });
      onClose();
    } catch (e) {
      toast.error(errorMessage(e));
    }
  };

  const restore = async () => {
    if (!item) return;
    await inv.restoreItem(item.id);
    qc.invalidateQueries({ queryKey: ["inv"] });
    toast.success(t("Qayta tiklandi"));
    onClose();
  };

  const closeNew = () => {
    if (isNew && !form.device_type && !photos.length) localStorage.removeItem(DRAFT_KEY);
    onClose();
  };

  return (
    <Overlay open onClose={closeNew} wide
      title={isNew ? t("Yangi qurilma") : item?.inv_number}
      subtitle={isNew ? t("Inventar raqamni tizim o'zi beradi") : `${names.type(item!.device_type, item!.device_type_name)} · ${item?.branch_name}`}
      footer={canWrite ? (
        <div className="flex gap-2">
          {isNew && (
            <Btn variant="outline" size="lg" className="flex-1" loading={saving === "more"} disabled={!!saving} onClick={() => save(true)}>
              <Plus className="size-4" />{t("Saqlash va yana")}
            </Btn>
          )}
          <Btn size="lg" className="flex-1" loading={saving === "save"} disabled={!!saving} onClick={() => save(false)}>{t("Saqlash")}</Btn>
        </div>
      ) : item?.is_deleted && boot.me.can.write ? (
        <Btn size="lg" className="w-full" onClick={restore}><RotateCcw className="size-4" />{t("Qayta tiklash")}</Btn>
      ) : undefined}>
      <div id="inv-form-top" className="space-y-4 p-4">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("Filial")} required>
            {fixedBranch ? (
              <div className="flex h-12 items-center gap-2 rounded-xl border bg-muted/50 px-3 text-[15px] font-medium md:h-10 md:rounded-lg md:text-sm">
                <MapPin className="size-4 text-primary" />{boot.branches.find((b) => b.id === form.branch)?.name}
              </div>
            ) : (
              <Picker title={t("Filial")} value={form.branch ? String(form.branch) : ""} options={branchOpts} invalid={errors.branch}
                disabled={!canWrite} icon={<MapPin className="size-4" />}
                onChange={(v) => { set("branch", v ? Number(v) : null); set("employee", null); }} />
            )}
          </Field>
          <Field label={t("Tashkilot (loyiha)")}>
            <Picker title={t("Tashkilot")} value={form.org ? String(form.org) : ""} options={orgOpts} disabled={!canWrite}
              onChange={(v) => set("org", v ? Number(v) : null)} />
          </Field>
        </div>

        <Field label={t("Qurilma turi")} required>
          <Picker title={t("Qurilma turi")} value={form.device_type ? String(form.device_type) : ""} options={typeOpts}
            invalid={errors.device_type} disabled={!canWrite} placeholder={t("Nima ekanini tanlang")}
            icon={type ? <GroupIcon group={type.group} className="size-4" /> : <Package className="size-4" />}
            onChange={(v) => { set("device_type", v ? Number(v) : null); set("brand", ""); }} />
        </Field>
        {type && (type.serial_hint || type.extra_hint) && (
          <div className="flex gap-3 rounded-xl border border-amber-500/30 bg-amber-500/8 p-3 text-sm">
            <Info className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <div className="space-y-1">
              {type.serial_hint && <div><b>{t("Seriya raqami:")}</b> {loc(type, "serial_hint", lang)}</div>}
              {type.extra_hint && <div><b>{t("Qo'shimcha:")}</b> {loc(type, "extra_hint", lang)}</div>}
            </div>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <Field label={t("Brend")}>
            <Picker title={t("Brend")} value={form.brand} options={brandOpts} allowCustom disabled={!canWrite || !type}
              placeholder={type ? t("Tanlang yoki yozing") : t("Avval qurilma turini tanlang")} onChange={(v) => set("brand", v)} />
          </Field>
          <Field label={t("Model")}>
            <input className={inputCls} value={form.model} disabled={!canWrite} onChange={(e) => set("model", e.target.value)}
              placeholder={t("masalan: ThinkPad E14")} />
          </Field>
        </div>

        <Field label={t("Seriya raqami (S/N)")} hint={!form.serial ? t("Topa olmasangiz — bo'sh qoldiring va izohga «yorliq yo'q» deb yozing. Taxminan yozmang.") : undefined}>
          <input className={cn(inputCls, "font-mono uppercase")} value={form.serial} disabled={!canWrite}
            onChange={(e) => { set("serial", e.target.value); setDup(null); }} onBlur={checkSerial}
            autoCapitalize="characters" autoCorrect="off" spellCheck={false} placeholder="SN-998811-X" />
        </Field>
        {dup && (
          <div className="flex gap-2 rounded-xl border border-red-500/30 bg-red-500/8 p-3 text-sm text-red-700 dark:text-red-400">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>{t("Bu seriya raqam allaqachon kiritilgan: {n} ({b}). Qayta kiritmayapsizmi?", { n: dup.inv_number, b: dup.branch })}</span>
          </div>
        )}

        <div className="grid grid-cols-1 gap-3 sm:grid-cols-[160px_1fr]">
          <Field label={t("Soni")} hint={t("Bir xil 5 ta sichqoncha — bitta qator, soni 5")}>
            <Stepper value={form.quantity} onChange={(n) => set("quantity", n)} />
          </Field>
          <Field label={t("Holati")}>
            <ConditionChips value={form.condition} onChange={(v) => set("condition", v)} options={boot.conditions} />
          </Field>
        </div>

        <Field label={t("Kimda turibdi (xodim)")} hint={t("Router, printer kabi umumiy qurilmalarda — unga javobgar xodimni tanlang")}>
          <Picker title={t("Xodim")} value={form.employee ? String(form.employee) : ""} options={empOpts} disabled={!canWrite || !form.branch}
            placeholder={form.branch ? (employees.isLoading ? t("Yuklanmoqda…") : t("Xodimni tanlang")) : t("Avval filialni tanlang")}
            icon={<User className="size-4" />} createLabel={t("Yangi xodim qo'shish")}
            onCreate={async (name) => {
              const created = await inv.createEmployee({ full_name: name, branch: form.branch, org: form.org });
              await qc.invalidateQueries({ queryKey: ["inv", "employees"] });
              set("employee", created.id);
              toast.success(t("Xodim qo'shildi: {n}", { n: created.full_name }));
            }}
            onChange={(v) => set("employee", v ? Number(v) : null)} />
        </Field>
        {emp?.position && <div className="-mt-2 text-xs text-muted-foreground">{emp.position}</div>}
        {contact && (
          <ContactBlock contact={contact} disabled={!canWrite} invalid={{ phone: errors.phone, telegram: errors.telegram }}
            onChange={(c) => { setContactEdit(c); setErrors((e) => ({ ...e, phone: false, telegram: false })); }} />
        )}

        <Field label={t("Qayerda turibdi")}>
          <Picker title={t("Qayerda turibdi")} value={form.location} options={locOpts} allowCustom disabled={!canWrite}
            icon={<MapPin className="size-4" />} onChange={(v) => set("location", v)} />
        </Field>

        <PhotoBlock photos={photos} setPhotos={setPhotos} disabled={!canWrite} />

        <Field label={t("Izoh")}>
          <textarea className={cn(inputCls, "h-auto min-h-20 py-2.5 md:h-auto")} value={form.note} disabled={!canWrite}
            onChange={(e) => set("note", e.target.value)} placeholder={(type && loc(type, "extra_hint", lang)) || t("Qo'shimcha ma'lumot")} />
        </Field>

        <PurchaseBlock form={form} set={set} disabled={!canWrite} />

        {item && (
          <div className="space-y-3 border-t pt-4">
            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <div>{t("Kiritdi:")} <b className="text-foreground">{item.created_by || "—"}</b><br />{dt(item.created_at)}</div>
              <div>{t("O'zgartirdi:")} <b className="text-foreground">{item.updated_by || "—"}</b><br />{dt(item.updated_at)}</div>
            </div>
            {!!detail.data?.history?.length && (
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground"><History className="size-3.5" />{t("Tarix")}</div>
                <div className="space-y-1.5">
                  {detail.data.history.map((h) => (
                    <div key={h.id} className="rounded-lg bg-muted/50 px-3 py-2 text-xs">
                      <div className="flex justify-between gap-2"><b>{actionLabel(h.action, lang)} · {h.user}</b><span className="text-muted-foreground">{ago(h.at)}</span></div>
                      {Object.entries(h.changes || {}).map(([k, v]) => (
                        <div key={k} className="mt-0.5 text-muted-foreground">{fieldLabel(k, lang)}: <s>{String(v[0] ?? "")}</s> → {String(v[1] ?? "")}</div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {canWrite && (confirmDel ? (
              <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3">
                <span className="flex-1 text-sm">{t("O'chirilsinmi? (keyin qaytarish mumkin)")}</span>
                <Btn variant="outline" size="sm" onClick={() => setConfirmDel(false)}>{t("Yo'q")}</Btn>
                <Btn variant="danger" size="sm" onClick={remove}>{t("Ha, o'chirish")}</Btn>
              </div>
            ) : (
              <Btn variant="danger" className="w-full" onClick={() => setConfirmDel(true)}><Trash2 className="size-4" />{t("O'chirish")}</Btn>
            ))}
          </div>
        )}
      </div>
    </Overlay>
  );
}

/* ------------------------------------------------------------------ ro'yxat */
export function ItemCard({ it, onClick }: { it: Item; onClick: () => void }) {
  const t = useT();
  const names = useCatalogNames();
  const photo = it.photos[0];
  return (
    <button onClick={onClick} className={cn("flex w-full gap-3 rounded-2xl border bg-card p-3 text-left shadow-xs transition-colors hover:border-primary/40 active:bg-muted/50",
      it.is_deleted && "opacity-60")}>
      <div className="relative size-16 shrink-0 overflow-hidden rounded-xl bg-muted">
        {photo ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={photo.thumb} alt="" loading="lazy" className="size-full object-cover" />
        ) : (
          <div className="grid size-full place-items-center text-muted-foreground"><GroupIcon group={it.group} className="size-6" /></div>
        )}
        {it.photos.length > 1 && <span className="absolute bottom-0.5 right-0.5 rounded bg-black/60 px-1 text-[10px] font-semibold text-white">{it.photos.length}</span>}
      </div>
      <div className="min-w-0 flex-1">
        <div className="flex items-start gap-2">
          <div className="min-w-0 flex-1 truncate text-[15px] font-semibold">{names.type(it.device_type, it.device_type_name)}</div>
          {it.quantity > 1 && <span className="shrink-0 rounded-md bg-muted px-1.5 text-xs font-bold">×{it.quantity}</span>}
        </div>
        <div className="truncate text-sm text-muted-foreground">{[it.brand, it.model].filter(Boolean).join(" ") || "—"}</div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="font-mono font-semibold text-primary">{it.inv_number}</span>
          <CondBadge value={it.condition} />
          {it.is_deleted && <span className="rounded-full bg-red-500/10 px-2 text-[11px] font-semibold text-red-600">{t("O'chirilgan")}</span>}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          {it.employee_name ? <span className="inline-flex items-center gap-1"><User className="size-3" />{it.employee_name}</span>
            : <span className="text-amber-600">{t("xodim yo'q")}</span>}
          {!it.serial && <span className="text-amber-600">{t("S/N yo'q")}</span>}
          {warrantyState(it.warranty_until) === "expired" && <span className="text-red-600">{t("kafolat tugagan")}</span>}
          <span>{it.branch_name}{it.location ? ` · ${names.place(it.location)}` : ""}</span>
          <span>{ago(it.updated_at)}</span>
        </div>
      </div>
    </button>
  );
}

export interface ItemFilters {
  q?: string; branch?: string; org?: string; type?: string; condition?: string; group?: string; employee?: string;
  no_serial?: boolean; no_employee?: boolean; no_photo?: boolean; mine?: boolean; deleted?: boolean; warranty?: string;
}

function ItemsTable({ rows, onOpen }: { rows: Item[]; onOpen: (it: Item) => void }) {
  const t = useT();
  const names = useCatalogNames();
  return (
    <div className="hidden overflow-x-auto rounded-xl border bg-card md:block">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-14 px-3 py-2.5" />
            <th className="px-2 py-2.5 font-semibold">{t("Inv. raqam")}</th>
            <th className="px-2 py-2.5 font-semibold">{t("Qurilma")}</th>
            <th className="px-2 py-2.5 font-semibold">{t("Seriya (S/N)")}</th>
            <th className="px-2 py-2.5 text-right font-semibold">{t("Soni")}</th>
            <th className="px-2 py-2.5 font-semibold">{t("Holati")}</th>
            <th className="px-2 py-2.5 font-semibold">{t("Kimda")}</th>
            <th className="px-2 py-2.5 font-semibold">{t("Filial · joy")}</th>
            <th className="px-2 py-2.5 font-semibold">{t("Kafolat")}</th>
            <th className="px-3 py-2.5 font-semibold">{t("Yangilangan")}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((it) => (
            <tr key={it.id} onClick={() => onOpen(it)} className={cn("cursor-pointer border-b last:border-0 hover:bg-muted/40", it.is_deleted && "opacity-60")}>
              <td className="px-3 py-1.5">
                <div className="relative size-10 overflow-hidden rounded-lg bg-muted">
                  {it.photos[0] ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={it.photos[0].thumb} alt="" loading="lazy" className="size-full object-cover" />
                  ) : <div className="grid size-full place-items-center text-muted-foreground"><GroupIcon group={it.group} className="size-4" /></div>}
                  {it.photos.length > 1 && <span className="absolute bottom-0 right-0 rounded-tl bg-black/60 px-1 text-[9px] font-semibold text-white">{it.photos.length}</span>}
                </div>
              </td>
              <td className="whitespace-nowrap px-2 font-mono text-xs font-semibold text-primary">{it.inv_number}</td>
              <td className="px-2"><div className="font-medium">{names.type(it.device_type, it.device_type_name)}</div><div className="text-xs text-muted-foreground">{[it.brand, it.model].filter(Boolean).join(" ") || "—"}</div></td>
              <td className="px-2 font-mono text-xs">{it.serial || <span className="font-sans text-amber-600">{t("yo'q")}</span>}</td>
              <td className="px-2 text-right tabular-nums">{it.quantity}</td>
              <td className="px-2"><CondBadge value={it.condition} />{it.is_deleted && <div className="mt-0.5 text-[11px] text-red-600">{t("o'chirilgan")}</div>}</td>
              <td className="px-2">{it.employee_name ? <><div>{it.employee_name}</div><div className="text-xs text-muted-foreground">{it.employee_position}</div></> : <span className="text-xs text-amber-600">{t("biriktirilmagan")}</span>}</td>
              <td className="px-2"><div>{it.branch_name}</div><div className="text-xs text-muted-foreground">{names.place(it.location) || "—"}</div></td>
              <td className="whitespace-nowrap px-2 text-xs">
                {it.warranty_until ? <span className={WARRANTY_STYLE[warrantyState(it.warranty_until)]}>{dmy(it.warranty_until)}</span> : <span className="text-muted-foreground">—</span>}
                {it.purchase_price ? <div className="text-muted-foreground">{money(it.purchase_price)} {t("so'm")}</div> : null}
              </td>
              <td className="whitespace-nowrap px-3 text-xs text-muted-foreground">{ago(it.updated_at)}<div>{it.updated_by}</div></td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function ItemsView({ initial, onAdd, table }: { initial?: ItemFilters; onAdd: () => void; table?: boolean }) {
  const boot = useBoot().data!;
  const t = useT();
  const lang = useLang();
  const names = useCatalogNames();
  const [f, setF] = useState<ItemFilters>(initial ?? {});
  const [q, setQ] = useState(initial?.q ?? "");
  const [edit, setEdit] = useState<Item | null>(null);
  useEffect(() => {
    const tm = setTimeout(() => setF((x) => ({ ...x, q })), 300);
    return () => clearTimeout(tm);
  }, [q]);

  const params: Params = {
    q: f.q, branch: f.branch, org: f.org, type: f.type, condition: f.condition, group: f.group, employee: f.employee,
    no_serial: f.no_serial ? 1 : undefined, no_employee: f.no_employee ? 1 : undefined, no_photo: f.no_photo ? 1 : undefined,
    mine: f.mine ? 1 : undefined, deleted: f.deleted ? 1 : undefined, warranty: f.warranty,
  };
  const list = useInfiniteQuery({
    queryKey: ["inv", "items", params],
    queryFn: ({ pageParam }) => inv.items({ ...params, page: pageParam, page_size: 30 }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page * last.page_size < last.count ? last.page + 1 : undefined),
  });
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const first = list.data?.pages[0];
  const setKey = <K extends keyof ItemFilters>(key: K, value: ItemFilters[K]) => setF((x) => ({ ...x, [key]: value || undefined }));
  const toggle = (key: keyof ItemFilters) => setF((x) => ({ ...x, [key]: !x[key] || undefined }));
  const branchOpts = boot.branches.map((b) => ({ value: String(b.id), label: b.name }));
  const typeOpts = boot.device_types.map((d) => ({ value: String(d.id), label: loc(d, "name", lang), group: tr(d.group, undefined, lang) }));

  const chips: FilterChip[] = [];
  if (f.branch) chips.push({ label: boot.branches.find((b) => String(b.id) === f.branch)?.name ?? t("Filial"), onRemove: () => setKey("branch", undefined) });
  if (f.type) chips.push({ label: names.type(Number(f.type)), onRemove: () => setKey("type", undefined) });
  if (f.condition) chips.push({ label: condLabel(f.condition, lang), onRemove: () => setKey("condition", undefined) });
  if (f.org) chips.push({ label: boot.orgs.find((o) => String(o.id) === f.org)?.name ?? t("Tashkilot"), onRemove: () => setKey("org", undefined) });
  if (f.group) chips.push({ label: names.group(f.group), onRemove: () => setKey("group", undefined) });
  if (f.employee) chips.push({ label: rows[0]?.employee_name || t("Xodim"), onRemove: () => setKey("employee", undefined) });
  const warrantyOpts = [{ value: "expired", label: t("Kafolati tugagan") }, { value: "soon", label: t("90 kunda tugaydi") },
    { value: "active", label: t("Kafolatda") }, { value: "none", label: t("Kafolat kiritilmagan") }];
  if (f.warranty) chips.push({ label: warrantyOpts.find((o) => o.value === f.warranty)?.label ?? f.warranty, onRemove: () => setKey("warranty", undefined) });
  const quick: [keyof ItemFilters, string][] = [["mine", "Men kiritganlar"], ["no_serial", "S/N yo'q"], ["no_employee", "Xodimsiz"],
    ["no_photo", "Rasmsiz"], ["deleted", "O'chirilganlar"]];
  for (const [k, label] of quick) if (f[k]) chips.push({ label: t(label), onRemove: () => toggle(k) });

  return (
    <div className={cn("mx-auto w-full", table ? "max-w-[1800px]" : "max-w-5xl")}>
      <FilterBar inline={table} search={q} onSearch={setQ} placeholder={t("Raqam, seriya, model, xodim…")} chips={chips}
        onClear={() => setF((x) => ({ q: x.q }))} total={first?.count}
        right={boot.me.can.write && !table ? <Btn className="hidden sm:inline-flex" onClick={onAdd}><Plus className="size-4" />{t("Qo'shish")}</Btn> : undefined}>
        {boot.branches.length > 1 && (
          <Field label={table ? "" : t("Filial")}>
            <Picker title={t("Filial")} placeholder={t("Barcha filiallar")} value={f.branch ?? ""} options={branchOpts} onChange={(v) => setKey("branch", v)} />
          </Field>
        )}
        <Field label={table ? "" : t("Qurilma turi")}>
          <Picker title={t("Qurilma turi")} placeholder={t("Barcha turlar")} value={f.type ?? ""} options={typeOpts} onChange={(v) => setKey("type", v)} />
        </Field>
        <Field label={table ? "" : t("Holati")}>
          <Picker title={t("Holati")} placeholder={t("Har qanday holat")} value={f.condition ?? ""}
            options={boot.conditions.map((c) => ({ value: c.value, label: condLabel(c.value, lang) }))} onChange={(v) => setKey("condition", v)} />
        </Field>
        <Field label={table ? "" : t("Tashkilot")}>
          <Picker title={t("Tashkilot")} placeholder={t("Barcha tashkilotlar")} value={f.org ?? ""}
            options={boot.orgs.map((o) => ({ value: String(o.id), label: o.name }))} onChange={(v) => setKey("org", v)} />
        </Field>
        <Field label={table ? "" : t("Kafolat")}>
          <Picker title={t("Kafolat")} placeholder={t("Kafolat: hammasi")} value={f.warranty ?? ""} options={warrantyOpts} onChange={(v) => setKey("warranty", v)} />
        </Field>
        <div className={cn(table ? "flex flex-wrap items-center gap-1.5 sm:col-span-3 lg:col-span-6" : "")}>
          {!table && <div className="mb-1.5 text-[13px] font-semibold text-foreground/80">{t("Tezkor tanlash")}</div>}
          <div className="flex flex-wrap gap-2">
            {quick.map(([k, label]) => <ToggleChip key={k} active={!!f[k]} onClick={() => toggle(k)}>{t(label)}</ToggleChip>)}
          </div>
        </div>
      </FilterBar>

      <div className="flex items-center justify-between px-4 pb-1 pt-3 text-sm text-muted-foreground">
        <span>{first ? t("{rows} qator · {qty} dona", { rows: first.count, qty: first.quantity ?? 0 }) : "…"}</span>
        <Btn variant="ghost" size="sm" onClick={() => download("items/export/", { ...params, fmt: "xlsx" }).catch((e) => toast.error(errorMessage(e)))}>
          <Download className="size-4" />Excel
        </Btn>
      </div>

      <div className="space-y-2 px-3 pb-28 sm:px-4">
        {list.isLoading && <Spinner />}
        {list.isError && <Empty icon={<AlertTriangle className="size-6" />} title={t("Yuklab bo'lmadi")} hint={errorMessage(list.error)} />}
        {!list.isLoading && !rows.length && (
          <Empty icon={<ImageOff className="size-6" />} title={chips.length || f.q ? t("Bu filtr bo'yicha hech narsa yo'q") : t("Hozircha qurilma yo'q")}
            hint={chips.length || f.q ? undefined : boot.me.can.write ? t("Birinchi qurilmani qo'shing — «+» tugmasini bosing.") : undefined}
            action={chips.length || f.q ? <Btn variant="outline" onClick={() => { setF({}); setQ(""); }}>{t("Filtrlarni tozalash")}</Btn>
              : boot.me.can.write ? <Btn onClick={onAdd}><Plus className="size-4" />{t("Qurilma qo'shish")}</Btn> : undefined} />
        )}
        {table && !!rows.length && <ItemsTable rows={rows} onOpen={setEdit} />}
        {rows.map((it) => <div key={it.id} className={cn(table && "md:hidden")}><ItemCard it={it} onClick={() => setEdit(it)} /></div>)}
        {list.hasNextPage && (
          <Btn variant="outline" className="w-full" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>{t("Yana ko'rsatish")}</Btn>
        )}
      </div>
      <ItemForm open={!!edit} item={edit} onClose={() => setEdit(null)} />
    </div>
  );
}
