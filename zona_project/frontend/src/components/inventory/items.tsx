"use client";
/* eslint-disable react/no-unescaped-entities -- o'zbekcha matnlardagi apostrof (o'z, ma'lumot) */

import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle, BatteryCharging, Camera, Download, Filter, History, ImageOff, ImagePlus, Info, Keyboard, Loader2,
  MapPin, Minus, Monitor, Package, Plus, Printer, Projector, RotateCcw, Router, ScanBarcode, Search, ShieldCheck,
  Smartphone, Trash2, User, X,
} from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { download, inv, type Boot, type Condition, type Item, type ItemInput, type Params, type PhotoRef } from "./api";
import {
  Btn, COND_STYLE, CondBadge, Empty, Field, Overlay, Picker, Spinner, ago, compressImage, dt, inputCls, useBoot,
  type Opt,
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

export function useEmployees(branch: number | null | undefined) {
  return useQuery({
    queryKey: ["inv", "employees", "branch", branch ?? 0],
    queryFn: () => inv.employees({ branch: branch ?? undefined, limit: 5000 }),
    staleTime: 60_000,
    enabled: branch !== undefined,
  });
}

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
    employee: preset?.employee ?? null, note: "", photos: [],
  };
}

function fromItem(it: Item): ItemInput {
  return {
    org: it.org, branch: it.branch, location: it.location, device_type: it.device_type, brand: it.brand, model: it.model,
    serial: it.serial, quantity: it.quantity, condition: it.condition, employee: it.employee, note: it.note,
    photos: it.photos.map((p) => p.id),
  };
}

/* ------------------------------------------------------------------ rasmlar */
function PhotoBlock({ photos, setPhotos, disabled }: {
  photos: PhotoRef[]; setPhotos: (p: PhotoRef[]) => void; disabled?: boolean;
}) {
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
      toast.success(`${added.length} ta rasm qo'shildi`);
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
        <span className="flex-1 text-sm font-semibold">Qurilma rasmlari</span>
        <span className="font-mono text-xs text-muted-foreground">{photos.length} ta rasm</span>
      </div>
      <div className="grid grid-cols-3 gap-2 sm:grid-cols-4">
        <button type="button" disabled={disabled || progress !== null} onClick={() => camera.current?.click()}
          className="flex aspect-square flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-emerald-500/40 bg-emerald-500/5 text-emerald-700 active:scale-95 dark:text-emerald-400">
          <Camera className="size-6" /><span className="text-xs font-semibold">Kamera</span>
        </button>
        <button type="button" disabled={disabled || progress !== null} onClick={() => gallery.current?.click()}
          className="flex aspect-square flex-col items-center justify-center gap-1.5 rounded-xl border-2 border-dashed border-indigo-500/40 bg-indigo-500/5 text-indigo-700 active:scale-95 dark:text-indigo-400">
          <ImagePlus className="size-6" /><span className="text-xs font-semibold">Galereya</span>
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
                className="absolute right-1 top-1 grid size-7 place-items-center rounded-full bg-black/60 text-white" aria-label="Olib tashlash">
                <X className="size-4" />
              </button>
            )}
          </div>
        ))}
      </div>
      <p className="mt-2 text-xs text-muted-foreground">Qurilmaning o'zini va seriya raqami yozilgan yorlig'ini suratga oling. Bir nechta rasm mumkin.</p>
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
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((o) => (
        <button key={o.value} type="button" onClick={() => onChange(o.value)}
          className={cn("h-11 rounded-xl border px-3 text-sm font-semibold transition-all",
            value === o.value ? cn(COND_STYLE[o.value], "border-current ring-2 ring-current/20") : "bg-card text-muted-foreground")}>
          {o.label}
        </button>
      ))}
    </div>
  );
}

function Stepper({ value, onChange }: { value: number; onChange: (n: number) => void }) {
  return (
    <div className="flex h-12 items-center overflow-hidden rounded-xl border bg-card">
      <button type="button" onClick={() => onChange(Math.max(1, value - 1))} className="grid h-full w-12 place-items-center hover:bg-muted"><Minus className="size-4" /></button>
      <input inputMode="numeric" value={value} onChange={(e) => onChange(Math.max(1, Number(e.target.value.replace(/\D/g, "")) || 1))}
        className="h-full min-w-0 flex-1 bg-transparent text-center text-lg font-semibold tabular-nums outline-none" />
      <button type="button" onClick={() => onChange(value + 1)} className="grid h-full w-12 place-items-center hover:bg-muted"><Plus className="size-4" /></button>
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
  if (!open) return null;
  if (!boot) return <Overlay open onClose={onClose} title="Qurilma"><Spinner /></Overlay>;
  return <ItemFormBody key={item?.id ?? "new"} boot={boot} onClose={onClose} item={item} preset={preset} />;
}

function ItemFormBody({ boot, onClose, item, preset }: {
  boot: Boot; onClose: () => void; item?: Item | null; preset?: Partial<ItemInput>;
}) {
  const open = true;
  const qc = useQueryClient();
  // yangi qurilma uchun saqlanmagan qoralama tiklanadi
  const [restored] = useState<Draft | null>(() => (!item && !preset ? readDraft() : null));
  const [form, setForm] = useState<ItemInput | null>(() => (item ? fromItem(item) : restored?.form ?? emptyForm(boot, preset)));
  const [photos, setPhotos] = useState<PhotoRef[]>(() => (item ? item.photos : restored?.photos ?? []));
  const [saving, setSaving] = useState<"" | "save" | "more">("");
  const [errors, setErrors] = useState<Record<string, boolean>>({});
  const [dup, setDup] = useState<Item["duplicate"]>(null);
  const [confirmDel, setConfirmDel] = useState(false);
  const detail = useQuery({ queryKey: ["inv", "item", item?.id], queryFn: () => inv.item(item!.id), enabled: !!item });
  const isNew = !item;

  useEffect(() => {
    if (restored) toast.info("Saqlanmagan qoralama tiklandi");
  }, [restored]);

  // qoralama: yangi qurilma formasi har o'zgarganda saqlanadi (sahifa yangilansa yo'qolmaydi)
  useEffect(() => {
    if (!isNew || !form) return;
    try {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ form, photos }));
    } catch { /* joy yo'q */ }
  }, [form, photos, isNew]);

  const employees = useEmployees(form?.branch ?? null);
  const type = boot?.device_types.find((d) => d.id === form?.device_type);

  const typeOpts = useMemo<Opt[]>(() => (boot?.device_types ?? []).filter((d) => d.is_active || d.id === form?.device_type)
    .map((d) => ({ value: String(d.id), label: d.name, hint: d.description, group: d.group })), [boot, form?.device_type]);
  const brandOpts = useMemo<Opt[]>(() => (type?.brands ?? []).map((b) => ({ value: b, label: b })), [type]);
  const empOpts = useMemo<Opt[]>(() => (employees.data?.results ?? []).map((e) => ({
    value: String(e.id), label: e.full_name, hint: [e.position, e.project, e.phone].filter(Boolean).join(" · "),
  })), [employees.data]);
  const branchOpts = useMemo<Opt[]>(() => (boot?.branches ?? []).map((b) => ({ value: String(b.id), label: b.name, hint: b.region })), [boot]);
  const orgOpts = useMemo<Opt[]>(() => (boot?.orgs ?? []).map((o) => ({ value: String(o.id), label: o.name })), [boot]);
  const locOpts = useMemo<Opt[]>(() => (boot?.locations ?? []).map((l) => ({ value: l.name, label: l.name })), [boot]);

  if (!form) return null;

  const set = <K extends keyof ItemInput>(key: K, value: ItemInput[K]) => {
    setForm((f) => (f ? { ...f, [key]: value } : f));
    setErrors((e) => ({ ...e, [key]: false }));
  };
  const canWrite = boot.me.can.write && !item?.is_deleted;
  const fixedBranch = boot.me.branches?.length === 1;
  const emp = employees.data?.results.find((e) => e.id === form.employee);

  const checkSerial = async () => {
    if (form.serial.trim().length < 3) return setDup(null);
    try {
      setDup((await inv.checkSerial(form.serial.trim(), item?.id)).duplicate);
    } catch { /* tekshiruv ixtiyoriy */ }
  };

  const save = async (more: boolean) => {
    const errs = { device_type: !form.device_type, branch: !form.branch };
    setErrors(errs);
    if (errs.device_type || errs.branch) {
      toast.error(errs.branch ? "Filialni tanlang" : "Qurilma turini tanlang");
      return;
    }
    setSaving(more ? "more" : "save");
    try {
      const body = { ...form, photos: photos.map((p) => p.id) };
      const saved = item ? await inv.updateItem(item.id, body) : await inv.createItem(body);
      localStorage.setItem(LAST_KEY, JSON.stringify({ org: form.org, branch: form.branch, location: form.location }));
      if (isNew) localStorage.removeItem(DRAFT_KEY);
      qc.invalidateQueries({ queryKey: ["inv"], predicate: (q) => q.queryKey[1] !== "boot" });
      toast.success(`${saved.inv_number} saqlandi`, {
        description: saved.duplicate ? `Diqqat: bu seriya raqam ${saved.duplicate.inv_number} (${saved.duplicate.branch}) da ham bor` : undefined,
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
      toast.success(`${item.inv_number} o'chirildi`, {
        action: { label: "Qaytarish", onClick: () => inv.restoreItem(item.id).then(() => qc.invalidateQueries({ queryKey: ["inv"] })) },
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
    toast.success("Qayta tiklandi");
    onClose();
  };

  const closeNew = () => {
    if (isNew && !form.device_type && !photos.length) localStorage.removeItem(DRAFT_KEY);
    onClose();
  };

  return (
    <Overlay open={open} onClose={closeNew} wide
      title={isNew ? "Yangi qurilma" : item?.inv_number}
      subtitle={isNew ? "Inventar raqamni tizim o'zi beradi" : `${item?.device_type_name} · ${item?.branch_name}`}
      footer={canWrite ? (
        <div className="flex gap-2">
          {isNew && (
            <Btn variant="outline" size="lg" className="flex-1" loading={saving === "more"} disabled={!!saving} onClick={() => save(true)}>
              <Plus className="size-4" />Saqlash va yana
            </Btn>
          )}
          <Btn size="lg" className="flex-1" loading={saving === "save"} disabled={!!saving} onClick={() => save(false)}>Saqlash</Btn>
        </div>
      ) : item?.is_deleted && boot.me.can.write ? (
        <Btn size="lg" className="w-full" onClick={restore}><RotateCcw className="size-4" />Qayta tiklash</Btn>
      ) : undefined}>
      <div id="inv-form-top" className="space-y-4 p-4">
        {/* filial va tashkilot */}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Filial" required>
            {fixedBranch ? (
              <div className="flex h-12 items-center gap-2 rounded-xl border bg-muted/50 px-3 text-[15px] font-medium">
                <MapPin className="size-4 text-primary" />{boot.branches.find((b) => b.id === form.branch)?.name}
              </div>
            ) : (
              <Picker title="Filial" value={form.branch ? String(form.branch) : ""} options={branchOpts} invalid={errors.branch}
                disabled={!canWrite} icon={<MapPin className="size-4" />}
                onChange={(v) => { set("branch", v ? Number(v) : null); set("employee", null); }} />
            )}
          </Field>
          <Field label="Tashkilot (loyiha)">
            <Picker title="Tashkilot" value={form.org ? String(form.org) : ""} options={orgOpts} disabled={!canWrite}
              onChange={(v) => set("org", v ? Number(v) : null)} />
          </Field>
        </div>

        {/* qurilma turi */}
        <Field label="Qurilma turi" required>
          <Picker title="Qurilma turi" value={form.device_type ? String(form.device_type) : ""} options={typeOpts}
            invalid={errors.device_type} disabled={!canWrite} placeholder="Nima ekanini tanlang"
            icon={type ? <GroupIcon group={type.group} className="size-4" /> : <Package className="size-4" />}
            onChange={(v) => { set("device_type", v ? Number(v) : null); set("brand", ""); }} />
        </Field>
        {type && (type.serial_hint || type.extra_hint) && (
          <div className="flex gap-3 rounded-xl border border-amber-500/30 bg-amber-500/8 p-3 text-sm">
            <Info className="mt-0.5 size-4 shrink-0 text-amber-600" />
            <div className="space-y-1">
              {type.serial_hint && <div><b>Seriya raqami:</b> {type.serial_hint}</div>}
              {type.extra_hint && <div><b>Qo'shimcha:</b> {type.extra_hint}</div>}
            </div>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Brend">
            <Picker title="Brend" value={form.brand} options={brandOpts} allowCustom disabled={!canWrite || !type}
              placeholder={type ? "Tanlang yoki yozing" : "Avval qurilma turini tanlang"} onChange={(v) => set("brand", v)} />
          </Field>
          <Field label="Model">
            <input className={inputCls} value={form.model} disabled={!canWrite} onChange={(e) => set("model", e.target.value)}
              placeholder="masalan: ThinkPad E14" />
          </Field>
        </div>

        <Field label="Seriya raqami (S/N)" hint={!form.serial ? "Topa olmasangiz — bo'sh qoldiring va izohga «yorliq yo'q» deb yozing. Taxminan yozmang." : undefined}>
          <input className={cn(inputCls, "font-mono uppercase")} value={form.serial} disabled={!canWrite}
            onChange={(e) => { set("serial", e.target.value); setDup(null); }} onBlur={checkSerial}
            autoCapitalize="characters" autoCorrect="off" spellCheck={false} placeholder="SN-998811-X" />
        </Field>
        {dup && (
          <div className="flex gap-2 rounded-xl border border-red-500/30 bg-red-500/8 p-3 text-sm text-red-700 dark:text-red-400">
            <AlertTriangle className="mt-0.5 size-4 shrink-0" />
            <span>Bu seriya raqam allaqachon kiritilgan: <b>{dup.inv_number}</b> ({dup.branch}). Qayta kiritmayapsizmi?</span>
          </div>
        )}

        <div className="grid gap-3 sm:grid-cols-[160px_1fr]">
          <Field label="Soni" hint="Bir xil 5 ta sichqoncha — bitta qator, soni 5">
            <Stepper value={form.quantity} onChange={(n) => set("quantity", n)} />
          </Field>
          <Field label="Holati">
            <ConditionChips value={form.condition} onChange={(v) => set("condition", v)} options={boot.conditions} />
          </Field>
        </div>

        <Field label="Kimda turibdi (xodim)" hint="Router, printer kabi umumiy qurilmalarda — unga javobgar xodimni tanlang">
          <Picker title="Xodim" value={form.employee ? String(form.employee) : ""} options={empOpts} disabled={!canWrite || !form.branch}
            placeholder={form.branch ? (employees.isLoading ? "Yuklanmoqda…" : "Xodimni tanlang") : "Avval filialni tanlang"}
            icon={<User className="size-4" />} createLabel="Yangi xodim qo'shish"
            onCreate={async (name) => {
              const created = await inv.createEmployee({ full_name: name, branch: form.branch, org: form.org });
              await qc.invalidateQueries({ queryKey: ["inv", "employees"] });
              set("employee", created.id);
              toast.success(`Xodim qo'shildi: ${created.full_name}`);
            }}
            onChange={(v) => set("employee", v ? Number(v) : null)} />
        </Field>
        {emp && (emp.position || emp.phone) && (
          <div className="-mt-2 text-xs text-muted-foreground">{[emp.position, emp.phone].filter(Boolean).join(" · ")}</div>
        )}

        <Field label="Qayerda turibdi">
          <Picker title="Qayerda turibdi" value={form.location} options={locOpts} allowCustom disabled={!canWrite}
            icon={<MapPin className="size-4" />} onChange={(v) => set("location", v)} />
        </Field>

        <PhotoBlock photos={photos} setPhotos={setPhotos} disabled={!canWrite} />

        <Field label="Izoh">
          <textarea className={cn(inputCls, "h-auto min-h-20 py-2.5")} value={form.note} disabled={!canWrite}
            onChange={(e) => set("note", e.target.value)} placeholder={type?.extra_hint || "Qo'shimcha ma'lumot"} />
        </Field>

        {item && (
          <div className="space-y-3 border-t pt-4">
            <div className="grid grid-cols-2 gap-2 text-xs text-muted-foreground">
              <div>Kiritdi: <b className="text-foreground">{item.created_by || "—"}</b><br />{dt(item.created_at)}</div>
              <div>O'zgartirdi: <b className="text-foreground">{item.updated_by || "—"}</b><br />{dt(item.updated_at)}</div>
            </div>
            {!!detail.data?.history?.length && (
              <div>
                <div className="mb-2 flex items-center gap-1.5 text-xs font-bold uppercase tracking-wider text-muted-foreground"><History className="size-3.5" />Tarix</div>
                <div className="space-y-1.5">
                  {detail.data.history.map((h) => (
                    <div key={h.id} className="rounded-lg bg-muted/50 px-3 py-2 text-xs">
                      <div className="flex justify-between gap-2"><b>{h.action_label} · {h.user}</b><span className="text-muted-foreground">{ago(h.at)}</span></div>
                      {Object.entries(h.changes || {}).map(([k, v]) => (
                        <div key={k} className="mt-0.5 text-muted-foreground">{k}: <s>{String(v[0] ?? "")}</s> → {String(v[1] ?? "")}</div>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            )}
            {canWrite && (confirmDel ? (
              <div className="flex items-center gap-2 rounded-xl border border-red-500/30 bg-red-500/5 p-3">
                <span className="flex-1 text-sm">O'chirilsinmi? (keyin qaytarish mumkin)</span>
                <Btn variant="outline" size="sm" onClick={() => setConfirmDel(false)}>Yo'q</Btn>
                <Btn variant="danger" size="sm" onClick={remove}>Ha, o'chirish</Btn>
              </div>
            ) : (
              <Btn variant="danger" className="w-full" onClick={() => setConfirmDel(true)}><Trash2 className="size-4" />O'chirish</Btn>
            ))}
          </div>
        )}
      </div>
    </Overlay>
  );
}

/* ------------------------------------------------------------------ ro'yxat */
function Chip({ active, onClick, children }: { active?: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <button onClick={onClick} className={cn("h-9 shrink-0 whitespace-nowrap rounded-full border px-3 text-[13px] font-medium transition-colors md:h-8 md:text-xs",
      active ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground")}>
      {children}
    </button>
  );
}

export function ItemCard({ it, onClick }: { it: Item; onClick: () => void }) {
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
          <div className="min-w-0 flex-1 truncate text-[15px] font-semibold">{it.device_type_name}</div>
          {it.quantity > 1 && <span className="shrink-0 rounded-md bg-muted px-1.5 text-xs font-bold">×{it.quantity}</span>}
        </div>
        <div className="truncate text-sm text-muted-foreground">{[it.brand, it.model].filter(Boolean).join(" ") || "—"}</div>
        <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs">
          <span className="font-mono font-semibold text-primary">{it.inv_number}</span>
          <CondBadge value={it.condition} label={it.condition_label} />
          {it.is_deleted && <span className="rounded-full bg-red-500/10 px-2 text-[11px] font-semibold text-red-600">O'chirilgan</span>}
        </div>
        <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
          {it.employee_name ? <span className="inline-flex items-center gap-1"><User className="size-3" />{it.employee_name}</span>
            : <span className="text-amber-600">xodim yo'q</span>}
          {!it.serial && <span className="text-amber-600">S/N yo'q</span>}
          <span>{it.branch_name}{it.location ? ` · ${it.location}` : ""}</span>
          <span>{ago(it.updated_at)}</span>
        </div>
      </div>
    </button>
  );
}

export interface ItemFilters {
  q?: string; branch?: string; org?: string; type?: string; condition?: string; group?: string; employee?: string;
  no_serial?: boolean; no_employee?: boolean; no_photo?: boolean; mine?: boolean; deleted?: boolean;
}

function ItemsTable({ rows, onOpen }: { rows: Item[]; onOpen: (it: Item) => void }) {
  return (
    <div className="hidden overflow-x-auto rounded-xl border bg-card md:block">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
          <tr>
            <th className="w-14 px-3 py-2.5" />
            <th className="px-2 py-2.5 font-semibold">Inv. raqam</th>
            <th className="px-2 py-2.5 font-semibold">Qurilma</th>
            <th className="px-2 py-2.5 font-semibold">Seriya (S/N)</th>
            <th className="px-2 py-2.5 text-right font-semibold">Soni</th>
            <th className="px-2 py-2.5 font-semibold">Holati</th>
            <th className="px-2 py-2.5 font-semibold">Kimda</th>
            <th className="px-2 py-2.5 font-semibold">Filial · joy</th>
            <th className="px-3 py-2.5 font-semibold">Yangilangan</th>
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
              <td className="px-2"><div className="font-medium">{it.device_type_name}</div><div className="text-xs text-muted-foreground">{[it.brand, it.model].filter(Boolean).join(" ") || "—"}</div></td>
              <td className="px-2 font-mono text-xs">{it.serial || <span className="font-sans text-amber-600">yo'q</span>}</td>
              <td className="px-2 text-right tabular-nums">{it.quantity}</td>
              <td className="px-2"><CondBadge value={it.condition} label={it.condition_label} />{it.is_deleted && <div className="mt-0.5 text-[11px] text-red-600">o'chirilgan</div>}</td>
              <td className="px-2">{it.employee_name ? <><div>{it.employee_name}</div><div className="text-xs text-muted-foreground">{it.employee_position}</div></> : <span className="text-xs text-amber-600">biriktirilmagan</span>}</td>
              <td className="px-2"><div>{it.branch_name}</div><div className="text-xs text-muted-foreground">{it.location || "—"}</div></td>
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
  const [f, setF] = useState<ItemFilters>(initial ?? {});
  const [q, setQ] = useState(initial?.q ?? "");
  const [edit, setEdit] = useState<Item | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setF((x) => ({ ...x, q })), 300);
    return () => clearTimeout(t);
  }, [q]);

  const params: Params = {
    q: f.q, branch: f.branch, org: f.org, type: f.type, condition: f.condition, group: f.group, employee: f.employee,
    no_serial: f.no_serial ? 1 : undefined, no_employee: f.no_employee ? 1 : undefined, no_photo: f.no_photo ? 1 : undefined,
    mine: f.mine ? 1 : undefined, deleted: f.deleted ? 1 : undefined,
  };
  const list = useInfiniteQuery({
    queryKey: ["inv", "items", params],
    queryFn: ({ pageParam }) => inv.items({ ...params, page: pageParam, page_size: 30 }),
    initialPageParam: 1,
    getNextPageParam: (last) => (last.page * last.page_size < last.count ? last.page + 1 : undefined),
  });
  const rows = list.data?.pages.flatMap((p) => p.results) ?? [];
  const first = list.data?.pages[0];
  const toggle = (key: keyof ItemFilters) => setF((x) => ({ ...x, [key]: !x[key] }));
  const activeCount = ["branch", "org", "type", "condition", "group", "employee"].filter((k) => f[k as keyof ItemFilters]).length;
  const branchOpts = boot.branches.map((b) => ({ value: String(b.id), label: b.name }));
  const typeOpts = boot.device_types.map((d) => ({ value: String(d.id), label: d.name, group: d.group }));

  return (
    <div className={cn("mx-auto w-full", table ? "max-w-[1800px]" : "max-w-5xl")}>
      <div className="sticky top-[var(--inv-top,0px)] z-20 space-y-2 border-b bg-background/95 px-3 py-3 backdrop-blur sm:px-4">
        <div className="flex gap-2">
          <div className="flex h-11 min-w-0 flex-1 items-center gap-2 rounded-xl border bg-card px-3 focus-within:border-primary md:h-10 md:rounded-lg">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Raqam, seriya, model, xodim…"
              className="h-full min-w-0 flex-1 bg-transparent text-[15px] outline-none" />
            {q && <button onClick={() => setQ("")}><X className="size-4 text-muted-foreground" /></button>}
          </div>
          <button onClick={() => setShowFilters((s) => !s)}
            className={cn("relative grid size-11 shrink-0 place-items-center rounded-xl border bg-card", (showFilters || activeCount) && "border-primary text-primary", table && "hidden")}>
            <Filter className="size-4" />
            {!!activeCount && <span className="absolute -right-1 -top-1 grid size-5 place-items-center rounded-full bg-primary text-[10px] font-bold text-primary-foreground">{activeCount}</span>}
          </button>
          {boot.me.can.write && !table && <Btn className="hidden sm:inline-flex" onClick={onAdd}><Plus className="size-4" />Qo'shish</Btn>}
        </div>
        {(showFilters || table) && (
          <div className={cn("grid gap-2 sm:grid-cols-3", table && "lg:grid-cols-4")}>
            {boot.branches.length > 1 && (
              <Picker title="Filial" placeholder="Barcha filiallar" value={f.branch ?? ""} options={branchOpts}
                onChange={(v) => setF((x) => ({ ...x, branch: v || undefined }))} />
            )}
            <Picker title="Qurilma turi" placeholder="Barcha turlar" value={f.type ?? ""} options={typeOpts}
              onChange={(v) => setF((x) => ({ ...x, type: v || undefined }))} />
            <Picker title="Holati" placeholder="Har qanday holat" value={f.condition ?? ""}
              options={boot.conditions.map((c) => ({ value: c.value, label: c.label }))}
              onChange={(v) => setF((x) => ({ ...x, condition: v || undefined }))} />
            <Picker title="Tashkilot" placeholder="Barcha tashkilotlar" value={f.org ?? ""}
              options={boot.orgs.map((o) => ({ value: String(o.id), label: o.name }))}
              onChange={(v) => setF((x) => ({ ...x, org: v || undefined }))} />
          </div>
        )}
        <div className="-mx-3 flex gap-2 overflow-x-auto px-3 pb-0.5 [scrollbar-width:none] sm:mx-0 sm:px-0">
          <Chip active={f.mine} onClick={() => toggle("mine")}>Men kiritganlar</Chip>
          <Chip active={f.no_serial} onClick={() => toggle("no_serial")}>S/N yo'q</Chip>
          <Chip active={f.no_employee} onClick={() => toggle("no_employee")}>Xodimsiz</Chip>
          <Chip active={f.no_photo} onClick={() => toggle("no_photo")}>Rasmsiz</Chip>
          <Chip active={f.condition === "broken"} onClick={() => setF((x) => ({ ...x, condition: x.condition === "broken" ? undefined : "broken" }))}>Ishlamaydi</Chip>
          <Chip active={f.deleted} onClick={() => toggle("deleted")}>O'chirilganlar</Chip>
          {(activeCount > 0 || f.mine || f.no_serial || f.no_employee || f.no_photo || f.deleted || f.q) && (
            <Chip onClick={() => { setF({}); setQ(""); }}>Tozalash ✕</Chip>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between px-4 pb-1 pt-3 text-sm text-muted-foreground">
        <span>{first ? <><b className="text-foreground">{first.count}</b> qator · <b className="text-foreground">{first.quantity}</b> dona</> : "…"}</span>
        <div className="flex gap-1">
          <Btn variant="ghost" size="sm" onClick={() => download("items/export/", { ...params, fmt: "xlsx" }).catch((e) => toast.error(errorMessage(e)))}>
            <Download className="size-4" />Excel
          </Btn>
        </div>
      </div>

      <div className="space-y-2 px-3 pb-28 sm:px-4">
        {list.isLoading && <Spinner />}
        {list.isError && <Empty icon={<AlertTriangle className="size-6" />} title="Yuklab bo'lmadi" hint={errorMessage(list.error)} />}
        {!list.isLoading && !rows.length && (
          <Empty icon={<ImageOff className="size-6" />} title="Hozircha qurilma yo'q"
            hint={boot.me.can.write ? "Birinchi qurilmani qo'shing — «+» tugmasini bosing." : undefined}
            action={boot.me.can.write ? <Btn onClick={onAdd}><Plus className="size-4" />Qurilma qo'shish</Btn> : undefined} />
        )}
        {table && !!rows.length && <ItemsTable rows={rows} onOpen={setEdit} />}
        {rows.map((it) => <div key={it.id} className={cn(table && "md:hidden")}><ItemCard it={it} onClick={() => setEdit(it)} /></div>)}
        {list.hasNextPage && (
          <Btn variant="outline" className="w-full" loading={list.isFetchingNextPage} onClick={() => list.fetchNextPage()}>Yana ko'rsatish</Btn>
        )}
      </div>
      <ItemForm open={!!edit} item={edit} onClose={() => setEdit(null)} />
    </div>
  );
}
