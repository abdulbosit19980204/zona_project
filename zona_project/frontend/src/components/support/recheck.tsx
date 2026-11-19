"use client";

import { useQuery } from "@tanstack/react-query";
import { Pencil, RotateCcw, Sparkles } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi } from "./api";
import { fmtDate, Segmented, useSupportMutation } from "./common";
import type { ST } from "./i18n";

const PERIODS = ["24", "72", "168", "720"] as const;

/**
 * Qayta tekshirish: yaqinda (masalan, ko'rmasdan) tasdiqlangan javoblar. Belgilab — tasdiqlash navbatiga qaytarish
 * (bot ularni ishlatmay turadi) yoki AI'ga tekshirtirish (takliflar «AI takliflari»da, siz tasdiqlaysiz).
 */
export function Recheck({ t, onEdit }: { t: ST; onEdit: (id: number) => void }) {
  const can = useCan();
  const [hours, setHours] = useState<(typeof PERIODS)[number]>("24");
  const [sel, setSel] = useState<Set<number>>(new Set());
  const list = useQuery({ queryKey: ["support", "entries", "recheck", hours],
    queryFn: () => supportApi.entries({ status: "approved", approved_since: hours }) });
  const back = useSupportMutation(() => supportApi.bulk([...sel], "review"), (r) => t("rcBackDone", { n: r.done }));
  const ai = useSupportMutation(() => supportApi.startAIJob("entries", { ids: [...sel] }), t("rcAiStarted"));
  const rows = list.data ?? [];
  const all = rows.length > 0 && sel.size === rows.length;
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <div className="grid gap-3">
      <div className="sticky top-0 z-10 flex flex-wrap items-center gap-2 rounded-xl border bg-card/95 p-2.5 shadow-xs backdrop-blur">
        <span className="text-xs text-muted-foreground">{t("rcApprovedIn")}</span>
        <Segmented size="sm" value={hours} onChange={(v) => { setHours(v); setSel(new Set()); }}
          options={PERIODS.map((p) => ({ value: p, label: t(`rcP_${p}` as "rcP_24") }))} />
        {can.edit && rows.length > 0 && (
          <>
            <label className="ml-2 flex items-center gap-2 text-sm">
              <Checkbox checked={all ? true : sel.size ? "indeterminate" : false}
                onCheckedChange={() => setSel(all ? new Set() : new Set(rows.map((e) => e.id)))} />
              {sel.size ? t("selected", { n: sel.size }) : t("selectAll", { n: rows.length })}
            </label>
            <div className="ml-auto flex flex-wrap gap-2">
              <Button size="sm" variant="outline" disabled={!sel.size || back.isPending}
                onClick={() => back.mutate(undefined, { onSuccess: () => setSel(new Set()) })}>
                <RotateCcw className="size-4" />{t("rcBack")}
              </Button>
              <Button size="sm" disabled={!sel.size || sel.size > 200 || ai.isPending}
                onClick={() => ai.mutate(undefined, { onSuccess: () => setSel(new Set()) })}>
                <Sparkles className="size-4" />{t("rcAi")}
              </Button>
            </div>
          </>
        )}
      </div>
      {list.isLoading && <Skeleton className="h-48" />}
      {list.data && rows.length === 0 && <EmptyState icon={RotateCcw} title={t("rcNone")} />}
      {rows.map((e) => (
        <div key={e.id} className={cn("flex gap-3 rounded-xl border bg-card p-3 shadow-xs", sel.has(e.id) && "border-primary/50 bg-primary/[0.03]")}>
          {can.edit && <Checkbox className="mt-1" checked={sel.has(e.id)} onCheckedChange={() => toggle(e.id)} />}
          <div className="min-w-0 flex-1">
            <div className="font-medium leading-snug">{e.title}</div>
            <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">{e.answer}</p>
            <div className="mt-1 text-[11px] text-muted-foreground">
              {t("approvedBy")}: {e.approved_by || "—"} · {fmtDate(e.approved_at)} · {e.uses}× · 👍 {e.likes} · 👎 {e.dislikes}
            </div>
          </div>
          <Button size="sm" variant="ghost" className="shrink-0 self-start" onClick={() => onEdit(e.id)}><Pencil className="size-4" />{t("edit")}</Button>
        </div>
      ))}
    </div>
  );
}
