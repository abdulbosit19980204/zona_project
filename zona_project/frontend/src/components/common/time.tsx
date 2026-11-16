"use client";

import { Clock } from "lucide-react";
import { useTranslations } from "next-intl";

import type { Task } from "@/lib/api/types";
import { fmtHours, type LoadStatus, type TimeLoad } from "@/lib/model";
import { cn } from "@/lib/utils";

export const STATUS_COLOR: Record<LoadStatus, string> = { over: "var(--destructive)", busy: "var(--warning)", ok: "var(--success)" };

/** Savol vaqti: "10 daq · 12/hafta" (manba: taxmin / qo'lda / AI). */
export function TimeChip({ task, className }: { task: Pick<Task, "minutes" | "per_week" | "time_source">; className?: string }) {
  const t = useTranslations("time");
  if (!task.minutes) return null;
  return (
    <span
      title={t(`source.${task.time_source || "auto"}`)}
      className={cn("inline-flex items-center gap-1 rounded-full border bg-card px-2 py-0.5 font-mono text-[10.5px] text-muted-foreground", className)}
    >
      <Clock className="size-3" />
      {t("minutesShort", { n: task.minutes })}
      {task.per_week > 0 && <span>· {t("perWeekShort", { n: task.per_week })}</span>}
      {task.time_source !== "manual" && <span className="opacity-60">{task.time_source === "ai" ? "AI" : "≈"}</span>}
    </span>
  );
}

/** Bandlik chizig'i: mas'ul + zaxira soatlari, sig'im chegarasi bilan. */
export function LoadBar({ load, compact }: { load: TimeLoad; compact?: boolean }) {
  const t = useTranslations("time");
  const cap = Math.max(load.capacity, 0.1);
  const scale = Math.max(cap, load.hours) * 1.05;
  const color = STATUS_COLOR[load.status];
  return (
    <div className="min-w-0">
      {!compact && (
        <div className="mb-1 flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{t("weekLoad")}</span>
          <span className="font-mono">
            <b style={{ color }}>{fmtHours(load.hours)}</b> / {fmtHours(cap)} {t("h")} · <b style={{ color }}>{Math.round(load.util * 100)}%</b>
          </span>
        </div>
      )}
      <div className="relative h-2 overflow-hidden rounded-full bg-muted">
        <div className="absolute inset-y-0 left-0 rounded-l-full" style={{ width: `${(load.ownerMin / 60 / scale) * 100}%`, background: color }} />
        <div className="absolute inset-y-0 rounded-r-full opacity-45"
          style={{ left: `${(load.ownerMin / 60 / scale) * 100}%`, width: `${(load.backupMin / 60 / scale) * 100}%`, background: color }} />
        <div className="absolute inset-y-[-2px] w-0.5 bg-foreground/60" style={{ left: `${(cap / scale) * 100}%` }} title={t("capacity")} />
      </div>
    </div>
  );
}
