"use client";

import { useTranslations } from "next-intl";

import type { RoleKey } from "@/lib/api/types";
import { ROLE_DASH, ROLE_GLYPH } from "@/lib/model";
import { cn } from "@/lib/utils";

/** Rol belgisi: harf + chegara uslubi. Egasi — to'ldirilgan, tasdiqlovchi — binafsha shtrix. */
export function RoleGlyph({ role, count, className }: { role: RoleKey; count?: number; className?: string }) {
  const t = useTranslations("roles");
  return (
    <span
      title={t(role)}
      className={cn(
        "inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-[5px] border px-1 font-mono text-[10.5px] font-semibold",
        role === "owner" && "border-foreground bg-foreground text-background",
        role === "executor" && "border-border text-muted-foreground",
        role === "approver" && "border-dashed border-violet/60 text-violet",
        role === "supervisor" && "border-[3px] border-double border-border text-foreground",
        (role === "contributor" || role === "backup") && "border-dotted border-muted-foreground/60 text-muted-foreground",
        className,
      )}
    >
      {ROLE_GLYPH[role]}
      {count !== undefined && <span className="ml-0.5 font-normal">{count}</span>}
    </span>
  );
}

/** Chiziq namunasi (legenda uchun): xaritadagi bog'lanish qanday ko'rinishini ko'rsatadi. */
export function RoleLine({ role, width = 28 }: { role: RoleKey; width?: number }) {
  return (
    <svg width={width} height={8} viewBox={`0 0 ${width} 8`} aria-hidden className="shrink-0 text-[var(--edge-strong)]">
      <line
        x1={1} y1={4} x2={width - 1} y2={4} stroke="currentColor"
        strokeWidth={role === "owner" ? 2.2 : 1.6}
        strokeDasharray={ROLE_DASH[role]}
        strokeLinecap={role === "contributor" ? "round" : "butt"}
      />
    </svg>
  );
}

export function RoleLegend({ className }: { className?: string }) {
  const t = useTranslations("roles");
  const roles: RoleKey[] = ["owner", "executor", "approver", "supervisor", "contributor", "backup"];
  return (
    <div className={cn("grid gap-2 text-sm", className)}>
      {roles.map((r) => (
        <div key={r} className="flex items-center gap-2.5">
          <RoleLine role={r} />
          <RoleGlyph role={r} />
          <span>{t(r)}</span>
          <span className="ml-auto text-xs text-muted-foreground">{t(`hint.${r}`)}</span>
        </div>
      ))}
    </div>
  );
}
