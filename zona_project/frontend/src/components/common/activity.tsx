"use client";

import { formatDistanceToNow } from "date-fns";
import { enUS, ru, uz } from "date-fns/locale";
import { ArrowRightLeft, BadgeCheck, Pencil, Plus, Shield, Trash2, Users } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";

import type { AuditEvent, EventKind } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const ICON: Record<EventKind, typeof Plus> = {
  created: Plus, moved: ArrowRightLeft, edited: Pencil, deleted: Trash2, member: Users, role: Shield, approval: BadgeCheck,
};
export const DATE_LOCALES = { uz, ru, en: enUS } as const;

export function eventDetail(e: AuditEvent): string {
  if (e.kind === "moved") return `${e.from_name} → ${e.to_name}`;
  if (e.kind === "role") return `${e.to_name || e.from_name}: ${e.text}`;
  return e.text || (e.to_name ? e.to_name : e.from_name);
}

/** Tarix yozuvi: kim, nima, qachon. */
export function ActivityItem({ event, compact }: { event: AuditEvent; compact?: boolean }) {
  const t = useTranslations("events");
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const Icon = ICON[event.kind] ?? Pencil;
  return (
    <div className={cn("flex items-start gap-3", compact ? "py-2" : "py-3")}>
      <span
        className={cn(
          "mt-0.5 grid size-7 shrink-0 place-items-center rounded-lg border",
          event.kind === "deleted" && "text-destructive",
          event.kind === "approval" && "text-violet",
          event.kind === "moved" && "text-primary",
        )}
      >
        <Icon className="size-3.5" />
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium">{event.subject || event.to_name || event.from_name}</div>
        <div className="truncate text-xs text-muted-foreground">
          <span className="text-foreground/70">{t(event.kind)}</span> · {eventDetail(event)}
          {event.actor && <> · {event.actor}</>}
        </div>
      </div>
      <time className="shrink-0 text-[11px] text-muted-foreground" dateTime={event.at}>
        {formatDistanceToNow(new Date(event.at), { addSuffix: true, locale: DATE_LOCALES[locale] })}
      </time>
    </div>
  );
}
