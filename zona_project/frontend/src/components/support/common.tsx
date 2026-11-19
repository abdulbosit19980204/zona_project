"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronsUpDown, type LucideIcon } from "lucide-react";
import { useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Command, CommandEmpty, CommandInput, CommandItem, CommandList } from "@/components/ui/command";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import type { EntryStatus, Mode, MsgStatus } from "./api";
import type { SKey, ST } from "./i18n";

export { fmtDate } from "@/components/qrdrive/common";

const MSG_TONE: Record<MsgStatus, string> = {
  new: "border-primary/50 text-primary",
  answered: "border-success/50 text-success",
  drafted: "border-violet-500/50 text-violet-500",
  escalated: "border-warning/50 text-warning",
  ignored: "text-muted-foreground",
  closed: "text-muted-foreground",
};
const ENTRY_TONE: Record<EntryStatus, string> = {
  new: "border-primary/50 text-primary",
  review: "border-warning/50 text-warning",
  approved: "border-success/50 text-success",
  rejected: "border-destructive/50 text-destructive",
  archived: "text-muted-foreground",
};
const MODE_TONE: Record<Mode | "inherit", string> = {
  off: "text-muted-foreground",
  collect: "border-sky-500/50 text-sky-500",
  shadow: "border-violet-500/50 text-violet-500",
  live: "border-success/50 text-success",
  inherit: "text-muted-foreground",
};

export function MsgBadge({ status, t }: { status: MsgStatus; t: ST }) {
  return <Badge variant="outline" className={cn("font-normal", MSG_TONE[status])}>{t(`m_${status}` as SKey)}</Badge>;
}

export function EntryBadge({ status, t }: { status: EntryStatus; t: ST }) {
  return <Badge variant="outline" className={cn("font-normal", ENTRY_TONE[status])}>{t(`e_${status}` as SKey)}</Badge>;
}

export function ModeBadge({ mode, t }: { mode: Mode | "inherit"; t: ST }) {
  return <Badge variant="outline" className={cn("font-normal", MODE_TONE[mode])}>{t(`mode_${mode}` as SKey)}</Badge>;
}

export function stageLabel(stage: string, t: ST) {
  return stage ? t(`s_${stage}` as SKey) : "";
}

/** Mutatsiya: muvaffaqiyatda support so'rovlarini yangilaydi va xabar ko'rsatadi. */
export function useSupportMutation<V, R>(fn: (v: V) => Promise<R>, success?: string | ((r: R) => string)) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: ["support"] });
      if (success) toast.success(typeof success === "function" ? success(r) : success);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

/** Ko'p qatorli matn <-> ro'yxat. */
export const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
export const unlines = (a: string[] | undefined) => (a ?? []).join("\n");

/* ------------------------------------------------------------------ dizayn bloklari */

/** Segmentli tanlov (filtr va ko'rinishlar uchun): ixcham, sanoq bilan, kichik ekranda gorizontal aylanadi. */
export function Segmented<T extends string>({ value, options, onChange, className, size = "md" }: {
  value: T; onChange: (v: T) => void; className?: string; size?: "sm" | "md";
  options: { value: T; label: ReactNode; count?: number; icon?: LucideIcon }[];
}) {
  return (
    <div role="tablist" className={cn("inline-flex max-w-full items-center gap-0.5 overflow-x-auto rounded-lg bg-muted p-0.5", className)}>
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button key={o.value} type="button" role="tab" aria-selected={on} onClick={() => onChange(o.value)}
            className={cn("inline-flex shrink-0 items-center gap-1.5 rounded-md font-medium transition-all",
              size === "sm" ? "h-7 px-2.5 text-xs" : "h-8 px-3 text-sm",
              on ? "bg-background text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground")}>
            {o.icon && <o.icon className="size-3.5" />}
            {o.label}
            {o.count != null && o.count > 0 && (
              <span className={cn("rounded-full px-1.5 text-[10px] font-semibold tabular-nums leading-4",
                on ? "bg-primary text-primary-foreground" : "bg-foreground/10")}>{o.count}</span>
            )}
          </button>
        );
      })}
    </div>
  );
}

/** Sarlavhali panel: bir xil chegaralar, sarlavha satrida izoh va amallar. */
export function Panel({ title, hint, icon: Icon, actions, children, className, bodyClassName }: {
  title?: ReactNode; hint?: ReactNode; icon?: LucideIcon; actions?: ReactNode; children: ReactNode;
  className?: string; bodyClassName?: string;
}) {
  return (
    <section className={cn("overflow-hidden rounded-xl border bg-card shadow-xs", className)}>
      {(title || actions) && (
        <header className="flex items-start gap-3 border-b px-4 py-3">
          {Icon && <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg bg-primary/10 text-primary"><Icon className="size-4" /></span>}
          <div className="min-w-0 flex-1">
            {title && <h2 className="text-sm font-semibold leading-tight">{title}</h2>}
            {hint && <p className="mt-0.5 text-xs text-muted-foreground">{hint}</p>}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

/** Kichik ko'rsatkich: yorliq, katta raqam, ixtiyoriy izoh. */
export function Metric({ label, value, hint, icon: Icon, tone }: {
  label: string; value: ReactNode; hint?: ReactNode; icon?: LucideIcon; tone?: "success" | "warning" | "primary";
}) {
  return (
    <div className="flex min-w-0 items-center gap-3 rounded-xl border bg-card px-3.5 py-3 shadow-xs">
      {Icon && (
        <span className={cn("grid size-9 shrink-0 place-items-center rounded-lg bg-muted text-muted-foreground",
          tone === "success" && "bg-success/10 text-success", tone === "warning" && "bg-warning/10 text-warning",
          tone === "primary" && "bg-primary/10 text-primary")}>
          <Icon className="size-4" />
        </span>
      )}
      <div className="min-w-0">
        <div className="truncate text-xs text-muted-foreground">{label}</div>
        <div className="text-lg font-semibold tabular-nums leading-tight">{value}</div>
        {hint && <div className="truncate text-[11px] text-muted-foreground">{hint}</div>}
      </div>
    </div>
  );
}

const AVATAR_TONES = ["bg-sky-500/15 text-sky-600", "bg-violet-500/15 text-violet-600", "bg-emerald-500/15 text-emerald-600",
  "bg-amber-500/15 text-amber-600", "bg-rose-500/15 text-rose-600", "bg-cyan-500/15 text-cyan-600", "bg-indigo-500/15 text-indigo-600"];

/** Ism bosh harflari bilan rangli avatar (rang ismdan doimiy hisoblanadi). */
export function Initials({ name, className }: { name: string; className?: string }) {
  const n = (name || "?").trim() || "?";
  const parts = n.split(/\s+/).filter(Boolean);
  const text = (parts.length > 1 ? parts[0][0] + parts[1][0] : n.slice(0, 2)).toUpperCase();
  let h = 0;
  for (const ch of n) h = (h * 31 + ch.charCodeAt(0)) >>> 0;
  return (
    <span className={cn("grid size-9 shrink-0 place-items-center rounded-full text-xs font-semibold", AVATAR_TONES[h % AVATAR_TONES.length], className)}>
      {text}
    </span>
  );
}

/**
 * Javob tanlagich: qidiruvli ochiladigan ro'yxat. Uzun nomlar qatorga sig'adi (kesiladi, to'liq nomi — maslahatda),
 * yuzlab javob orasidan bir necha harf bilan topiladi.
 */
export function EntryPicker({ value, onChange, options, placeholder, searchPlaceholder, emptyText, hintId, hintLabel, className }: {
  value: string; onChange: (v: string) => void; options: { id: number; title: string }[];
  placeholder: string; searchPlaceholder: string; emptyText: string; hintId?: number | null; hintLabel?: string; className?: string;
}) {
  const [open, setOpen] = useState(false);
  const current = options.find((o) => String(o.id) === value);
  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger asChild>
        <Button type="button" variant="outline" role="combobox" aria-expanded={open} title={current?.title}
          className={cn("h-9 min-w-0 justify-between gap-2 font-normal", !current && "text-muted-foreground", className)}>
          <span className="truncate">{current?.title ?? placeholder}</span>
          <ChevronsUpDown className="size-4 shrink-0 opacity-50" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[min(30rem,calc(100vw-2rem))] p-0">
        <Command filter={(v, q) => (v.toLowerCase().includes(q.toLowerCase()) ? 1 : 0)}>
          <CommandInput placeholder={searchPlaceholder} />
          <CommandList className="max-h-72">
            <CommandEmpty>{emptyText}</CommandEmpty>
            {options.map((o) => (
              <CommandItem key={o.id} value={`${o.title} #${o.id}`} onSelect={() => { onChange(String(o.id)); setOpen(false); }}
                className="items-start gap-2">
                <Check className={cn("mt-0.5 size-4 shrink-0", String(o.id) === value ? "opacity-100" : "opacity-0")} />
                <span className="flex-1 leading-snug">{o.title}</span>
                {hintId === o.id && hintLabel && <Badge variant="outline" className="shrink-0 border-primary/40 font-normal text-primary">{hintLabel}</Badge>}
              </CommandItem>
            ))}
          </CommandList>
        </Command>
      </PopoverContent>
    </Popover>
  );
}
