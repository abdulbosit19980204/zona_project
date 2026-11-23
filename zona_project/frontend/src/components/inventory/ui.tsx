"use client";
/* eslint-disable react/no-unescaped-entities -- o'zbekcha matnlardagi apostrof (o'z, ma'lumot) */

import { useQuery } from "@tanstack/react-query";
import { formatDistanceToNowStrict } from "date-fns";
import { uz } from "date-fns/locale";
import { Check, ChevronDown, Loader2, Plus, Search, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { cn } from "@/lib/utils";

import { inv, type BranchStatus, type Condition, type Flag } from "./api";

/* ------------------------------------------------------------------ ma'lumot */
export function useBoot() {
  return useQuery({ queryKey: ["inv", "boot"], queryFn: inv.bootstrap, staleTime: 5 * 60_000 });
}

/* ------------------------------------------------------------------ matn qidiruvi (lotin / kirill, apostroflar) */
const CYR: Record<string, string> = {
  а: "a", б: "b", в: "v", г: "g", д: "d", е: "e", ё: "yo", ж: "j", з: "z", и: "i", й: "y", к: "k", л: "l", м: "m",
  н: "n", о: "o", п: "p", р: "r", с: "s", т: "t", у: "u", ф: "f", х: "x", ц: "ts", ч: "ch", ш: "sh", щ: "sh", ъ: "",
  ы: "i", ь: "", э: "e", ю: "yu", я: "ya", ў: "o'", қ: "q", ғ: "g'", ҳ: "h",
};
export function norm(text: string): string {
  return text.toLowerCase().replace(/[ʻʼ’‘`´]/g, "'").replace(/[а-яёўқғҳ]/g, (c) => CYR[c] ?? c).replace(/\s+/g, " ").trim();
}
export function matches(text: string, query: string): boolean {
  const q = norm(query);
  if (!q) return true;
  const t = norm(text);
  return q.split(" ").every((w) => t.includes(w));
}

/* ------------------------------------------------------------------ vaqt */
export function ago(value: string | null | undefined): string {
  if (!value) return "—";
  try {
    return formatDistanceToNowStrict(new Date(value), { addSuffix: true, locale: uz });
  } catch {
    return "—";
  }
}
export function dt(value: string | null | undefined): string {
  if (!value) return "—";
  const d = new Date(value);
  return `${d.toLocaleDateString("uz-UZ", { day: "2-digit", month: "2-digit", year: "numeric" })} ${d.toLocaleTimeString("uz-UZ", { hour: "2-digit", minute: "2-digit" })}`;
}

/* ------------------------------------------------------------------ telefon "orqaga" tugmasi oynani yopadi */
const overlayStack: (() => void)[] = [];
let ignorePop = 0;
let listening = false;
function onPop() {
  if (ignorePop > 0) {
    ignorePop -= 1;
    return;
  }
  overlayStack.pop()?.();
}
/** Oyna ochilganda tarixga yozuv qo'shadi: "orqaga" bosilsa saytdan chiqib ketmaydi, faqat oyna yopiladi. */
export function useBackClose(open: boolean, onClose: () => void) {
  const ref = useRef(onClose);
  useEffect(() => {
    ref.current = onClose;
  });
  useEffect(() => {
    if (!open || typeof window === "undefined") return;
    if (!listening) {
      window.addEventListener("popstate", onPop);
      listening = true;
    }
    let byBack = false;
    let pushed = false;
    const fn = () => {
      byBack = true;
      ref.current();
    };
    // kechiktirib yoziladi: darhol yopilgan (yoki StrictMode qayta o'rnatgan) oyna tarixni buzmasin
    const timer = window.setTimeout(() => {
      overlayStack.push(fn);
      window.history.pushState({ invOverlay: overlayStack.length }, "");
      pushed = true;
    }, 0);
    return () => {
      window.clearTimeout(timer);
      if (!pushed) return;
      const i = overlayStack.indexOf(fn);
      if (i >= 0) overlayStack.splice(i, 1);
      if (!byBack) {
        ignorePop += 1;
        window.history.back();
      }
    };
  }, [open]);
}

/* ------------------------------------------------------------------ oyna (telefonda — butun ekran) */
export function Overlay({ open, onClose, title, subtitle, children, footer, wide, z = 50 }: {
  open: boolean; onClose: () => void; title: ReactNode; subtitle?: ReactNode; children: ReactNode; footer?: ReactNode;
  wide?: boolean; z?: number;
}) {
  useBackClose(open, onClose);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="fixed inset-0 flex items-end justify-center bg-black/40 backdrop-blur-[2px] sm:items-center sm:p-4"
      style={{ zIndex: z }} onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={cn("flex h-[100dvh] w-full flex-col bg-background shadow-2xl sm:h-auto sm:max-h-[92dvh] sm:rounded-2xl sm:border",
        wide ? "sm:max-w-3xl" : "sm:max-w-lg")}>
        <div className="flex shrink-0 items-center gap-3 border-b px-4 py-3">
          <div className="min-w-0 flex-1">
            <div className="truncate text-base font-semibold">{title}</div>
            {subtitle && <div className="truncate text-xs text-muted-foreground">{subtitle}</div>}
          </div>
          <button onClick={onClose} className="grid size-10 place-items-center rounded-full hover:bg-muted" aria-label="Yopish">
            <X className="size-5" />
          </button>
        </div>
        <div className="min-h-0 flex-1 overflow-y-auto overscroll-contain">{children}</div>
        {footer && <div className="shrink-0 border-t bg-background px-4 py-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]">{footer}</div>}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ qidiruvli tanlov */
export interface Opt { value: string; label: string; hint?: string; group?: string }

export function Picker({ value, options, onChange, placeholder = "Tanlang", title, allowCustom, onCreate, createLabel,
  clearable = true, disabled, icon, invalid, className }: {
  value: string; options: Opt[]; onChange: (value: string, opt?: Opt) => void; placeholder?: string; title: string;
  allowCustom?: boolean; onCreate?: (text: string) => Promise<void> | void; createLabel?: string; clearable?: boolean;
  disabled?: boolean; icon?: ReactNode; invalid?: boolean; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [busy, setBusy] = useState(false);
  const current = options.find((o) => o.value === value);
  const label = current?.label ?? (allowCustom && value ? value : "");
  const filtered = useMemo(() => options.filter((o) => matches(`${o.label} ${o.hint ?? ""} ${o.group ?? ""}`, q)), [options, q]);
  const shown = filtered.slice(0, 250);
  const headers = shown.map((o, i) => (o.group && o.group !== shown[i - 1]?.group ? o.group : null));
  const exact = options.some((o) => norm(o.label) === norm(q));
  const close = () => {
    setOpen(false);
    setQ("");
  };
  const pick = (v: string, o?: Opt) => {
    onChange(v, o);
    close();
  };

  return (
    <>
      <button type="button" disabled={disabled} onClick={() => setOpen(true)}
        className={cn("flex h-12 w-full min-w-0 items-center gap-2 rounded-xl border bg-card px-3 text-left text-[15px] shadow-xs md:h-10 md:rounded-lg md:text-sm transition-colors hover:border-primary/40 disabled:opacity-60",
          invalid && "border-destructive ring-2 ring-destructive/15", className)}>
        {icon && <span className="shrink-0 text-muted-foreground">{icon}</span>}
        <span className={cn("min-w-0 flex-1 truncate", !label && "text-muted-foreground")}>{label || placeholder}</span>
        {clearable && value && !disabled ? (
          <span role="button" tabIndex={-1} onClick={(e) => { e.stopPropagation(); onChange(""); }}
            className="grid size-7 shrink-0 place-items-center rounded-full text-muted-foreground hover:bg-muted" aria-label="Tozalash">
            <X className="size-4" />
          </span>
        ) : <ChevronDown className="size-4 shrink-0 text-muted-foreground" />}
      </button>
      <Overlay open={open} onClose={close} title={title} z={70}>
        <div className="sticky top-0 z-10 border-b bg-background p-3">
          <div className="flex h-12 items-center gap-2 rounded-xl border bg-card px-3 focus-within:border-primary">
            <Search className="size-4 shrink-0 text-muted-foreground" />
            <input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder="Qidirish…"
              className="h-full min-w-0 flex-1 bg-transparent text-base outline-none" />
            {q && <button onClick={() => setQ("")} className="text-muted-foreground"><X className="size-4" /></button>}
          </div>
        </div>
        <div className="p-2 pb-6">
          {q && !exact && allowCustom && (
            <button onClick={() => pick(q.trim())} className="mb-1 flex w-full items-center gap-3 rounded-xl border border-dashed border-primary/40 px-3 py-3 text-left text-primary hover:bg-primary/5">
              <Plus className="size-4" /><span>«{q.trim()}» deb yozish</span>
            </button>
          )}
          {q && !exact && onCreate && (
            <button disabled={busy} onClick={async () => {
              setBusy(true);
              try { await onCreate(q.trim()); close(); } finally { setBusy(false); }
            }} className="mb-1 flex w-full items-center gap-3 rounded-xl border border-dashed border-primary/40 px-3 py-3 text-left text-primary hover:bg-primary/5">
              {busy ? <Loader2 className="size-4 animate-spin" /> : <Plus className="size-4" />}
              <span>{createLabel ?? "Yangi qo'shish"}: «{q.trim()}»</span>
            </button>
          )}
          {!q && onCreate && (
            <div className="mb-2 rounded-xl bg-muted/60 px-3 py-2 text-xs text-muted-foreground">
              Ro'yxatda yo'q bo'lsa — ismini yozing, pastda «{createLabel ?? "Yangi qo'shish"}» chiqadi.
            </div>
          )}
          {shown.map((o, i) => {
            const header = headers[i];
            return (
              <div key={o.value}>
                {header && <div className="px-3 pb-1 pt-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{header}</div>}
                <button onClick={() => pick(o.value, o)}
                  className={cn("flex w-full items-center gap-3 rounded-xl px-3 py-3 text-left hover:bg-muted active:bg-muted",
                    o.value === value && "bg-primary/10")}>
                  <div className="min-w-0 flex-1">
                    <div className="text-[15px] leading-snug">{o.label}</div>
                    {o.hint && <div className="mt-0.5 text-xs leading-snug text-muted-foreground">{o.hint}</div>}
                  </div>
                  {o.value === value && <Check className="size-5 shrink-0 text-primary" />}
                </button>
              </div>
            );
          })}
          {filtered.length > shown.length && (
            <div className="px-3 py-3 text-center text-xs text-muted-foreground">Yana {filtered.length - shown.length} ta — qidiruvni aniqlashtiring</div>
          )}
          {!filtered.length && !(q && (allowCustom || onCreate)) && (
            <div className="px-3 py-10 text-center text-sm text-muted-foreground">Hech narsa topilmadi</div>
          )}
        </div>
      </Overlay>
    </>
  );
}

/* ------------------------------------------------------------------ forma elementlari */
export function Field({ label, hint, children, required, className }: {
  label: string; hint?: ReactNode; children: ReactNode; required?: boolean; className?: string;
}) {
  return (
    <label className={cn("block min-w-0", className)}>
      <span className="mb-1.5 block text-[13px] font-semibold text-foreground/80">
        {label}{required && <span className="text-destructive"> *</span>}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs leading-snug text-muted-foreground">{hint}</span>}
    </label>
  );
}

export const inputCls = "h-12 w-full min-w-0 rounded-xl border bg-card px-3 text-[15px] shadow-xs md:h-10 md:rounded-lg md:text-sm outline-none transition-colors placeholder:text-muted-foreground focus:border-primary focus:ring-2 focus:ring-primary/15";

export function Btn({ children, onClick, variant = "primary", size = "md", disabled, loading, type = "button", className, title }: {
  children: ReactNode; onClick?: () => void; variant?: "primary" | "outline" | "ghost" | "danger" | "success" | "soft";
  size?: "sm" | "md" | "lg"; disabled?: boolean; loading?: boolean; type?: "button" | "submit"; className?: string; title?: string;
}) {
  return (
    <button type={type} onClick={onClick} disabled={disabled || loading} title={title}
      className={cn("inline-flex shrink-0 items-center justify-center gap-2 rounded-xl font-semibold transition-all active:translate-y-px disabled:pointer-events-none disabled:opacity-50",
        size === "sm" && "h-9 px-3 text-sm", size === "md" && "h-11 px-4 text-sm", size === "lg" && "h-13 px-5 text-base",
        variant === "primary" && "bg-indigo-600 text-white shadow-sm hover:bg-indigo-600/90",
        variant === "success" && "bg-success text-white shadow-sm hover:bg-success/90",
        variant === "outline" && "border bg-card hover:bg-muted",
        variant === "ghost" && "hover:bg-muted",
        variant === "soft" && "bg-indigo-500/10 text-indigo-600 hover:bg-indigo-500/15 dark:text-indigo-400",
        variant === "danger" && "bg-destructive/10 text-destructive hover:bg-destructive/20", className)}>
      {loading && <Loader2 className="size-4 animate-spin" />}
      {children}
    </button>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return <div className={cn("rounded-2xl border bg-card p-4 shadow-xs", className)}>{children}</div>;
}

export function SectionTitle({ icon, children, right }: { icon?: ReactNode; children: ReactNode; right?: ReactNode }) {
  return (
    <div className="mb-3 flex items-center gap-2">
      {icon && <span className="text-muted-foreground">{icon}</span>}
      <h3 className="flex-1 text-xs font-bold uppercase tracking-[0.1em] text-muted-foreground">{children}</h3>
      {right}
    </div>
  );
}

export function Empty({ icon, title, hint, action }: { icon?: ReactNode; title: string; hint?: string; action?: ReactNode }) {
  return (
    <div className="flex flex-col items-center px-6 py-14 text-center">
      {icon && <div className="mb-3 grid size-14 place-items-center rounded-2xl bg-muted text-muted-foreground">{icon}</div>}
      <div className="font-semibold">{title}</div>
      {hint && <p className="mt-1 max-w-sm text-sm text-muted-foreground">{hint}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return <div className={cn("grid place-items-center py-16", className)}><Loader2 className="size-6 animate-spin text-muted-foreground" /></div>;
}

/* ------------------------------------------------------------------ holat belgilari */
export const COND_STYLE: Record<Condition, string> = {
  ok: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400",
  repair: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  broken: "bg-red-500/12 text-red-700 dark:text-red-400",
  spare: "bg-sky-500/12 text-sky-700 dark:text-sky-400",
  missing: "bg-zinc-500/15 text-zinc-700 dark:text-zinc-300",
};
export const COND_COLOR: Record<Condition, string> = {
  ok: "#0ca30c", repair: "#fab219", broken: "#d03b3b", spare: "#2a78d6", missing: "#8a8a85",
};
export function CondBadge({ value, label }: { value: Condition; label: string }) {
  return <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold", COND_STYLE[value])}>{label}</span>;
}

export const STATUS_STYLE: Record<BranchStatus, string> = {
  planned: "bg-zinc-500/12 text-zinc-600 dark:text-zinc-300",
  active: "bg-blue-500/12 text-blue-700 dark:text-blue-400",
  done: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400",
};
export function StatusBadge({ value, label }: { value: BranchStatus; label: string }) {
  return <span className={cn("inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold", STATUS_STYLE[value])}>{label}</span>;
}

export const FLAG: Record<Flag, { label: string; cls: string; dot: string }> = {
  done: { label: "Yakunlandi", cls: "bg-emerald-500/12 text-emerald-700 dark:text-emerald-400", dot: "bg-emerald-500" },
  active: { label: "Faol", cls: "bg-blue-500/12 text-blue-700 dark:text-blue-400", dot: "bg-blue-500" },
  slowing: { label: "Sekinlashdi", cls: "bg-amber-500/15 text-amber-700 dark:text-amber-400", dot: "bg-amber-500" },
  slow: { label: "Sust", cls: "bg-red-500/12 text-red-700 dark:text-red-400", dot: "bg-red-500" },
  idle: { label: "Boshlanmagan", cls: "bg-zinc-500/15 text-zinc-600 dark:text-zinc-300", dot: "bg-zinc-400" },
};
export function FlagBadge({ value }: { value: Flag }) {
  const f = FLAG[value];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-semibold", f.cls)}>
      <span className={cn("size-1.5 rounded-full", f.dot)} />{f.label}
    </span>
  );
}

/* ------------------------------------------------------------------ rasmni telefonda siqish (tez yuklanadi) */
export async function compressImage(file: File, maxSide = 1600, quality = 0.82): Promise<File> {
  if (!file.type.startsWith("image/") || file.type === "image/gif") return file;
  try {
    const bitmap = await createImageBitmap(file, { imageOrientation: "from-image" });
    const scale = Math.min(1, maxSide / Math.max(bitmap.width, bitmap.height));
    if (scale === 1 && file.size < 900_000 && file.type === "image/jpeg") return file;
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * scale);
    canvas.height = Math.round(bitmap.height * scale);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, "image/jpeg", quality));
    if (!blob) return file;
    return new File([blob], file.name.replace(/\.\w+$/, "") + ".jpg", { type: "image/jpeg" });
  } catch {
    return file;  // eski brauzer — serverning o'zi siqadi
  }
}

/* ------------------------------------------------------------------ katta raqamli kartochka */
export function Kpi({ label, value, tone = "primary", hint, onClick }: {
  label: string; value: ReactNode; tone?: "primary" | "amber" | "green" | "violet" | "red" | "slate"; hint?: string; onClick?: () => void;
}) {
  const tones = {
    primary: "text-indigo-600 dark:text-indigo-400 border-indigo-500/20",
    amber: "text-amber-600 dark:text-amber-400 border-amber-500/25",
    green: "text-emerald-600 dark:text-emerald-400 border-emerald-500/25",
    violet: "text-violet-600 dark:text-violet-400 border-violet-500/25",
    red: "text-red-600 dark:text-red-400 border-red-500/25",
    slate: "text-slate-600 dark:text-slate-300 border-slate-500/25",
  };
  const Comp = onClick ? "button" : "div";
  return (
    <Comp onClick={onClick} className={cn("rounded-2xl border bg-card px-3 py-4 text-center", tones[tone], onClick && "transition-colors hover:bg-muted/50")}>
      <div className="text-[28px] font-bold leading-none tabular-nums">{value}</div>
      <div className="mt-2 text-xs font-medium opacity-90">{label}</div>
      {hint && <div className="mt-0.5 text-[11px] text-muted-foreground">{hint}</div>}
    </Comp>
  );
}

export function Progress({ value, className, tone = "bg-primary" }: { value: number; className?: string; tone?: string }) {
  return (
    <div className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}>
      <div className={cn("h-full rounded-full transition-all", tone)} style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}
