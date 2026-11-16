"use client";

import {
  ArrowRight, ArrowUpRight, Ban, CircleCheck, Eye, KeyRound, Pencil, Plus, Search, ShieldCheck, Star, Users,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { ZoneIcon } from "@/components/common/zone-icon";
import { LEVELS, MemberDialog } from "@/components/forms/member-dialog";
import { StaffContacts } from "@/components/views/staff-shared";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { useCan, useModel, useScope } from "@/hooks/use-org";
import type { Member, MemberLevel, Zone } from "@/lib/api/types";
import type { Model } from "@/lib/model";
import { cn } from "@/lib/utils";

const norm = (s: string) => s.toLowerCase().replace(/[ʻʼ’‘`´]/g, "'");

/** Daraja ranglari: murojaat yo'lidagi o'rni. */
export const LEVEL_COLOR: Record<MemberLevel, string> = {
  BIZ: "#22C55E", L1: "#06B6D4", L2: "#3B82F6", L3: "#8B5CF6", EXT: "#64748B", LEAD: "#F59E0B",
};
// murojaat yo'li: biznes -> birinchi yordam -> mutaxassis/dasturlash -> tashqi hamkor; nazorat — hammasining ustida
const FLOW: MemberLevel[] = ["BIZ", "L1", "L2", "L3", "EXT"];

export function LevelBadge({ level, className }: { level: MemberLevel | ""; className?: string }) {
  const t = useTranslations("people.levels");
  if (!level) return null;
  const c = LEVEL_COLOR[level];
  return (
    <span
      className={cn("inline-flex items-center rounded-full border px-2 py-0.5 text-[10.5px] font-semibold", className)}
      style={{ color: c, borderColor: `color-mix(in srgb, ${c} 45%, transparent)`, background: `color-mix(in srgb, ${c} 12%, transparent)` }}
    >
      {t(`${level}Short`)}
    </span>
  );
}

interface Coverage { zones: { zone: Zone | null; owner: number; backup: number }[]; owner: number; backup: number; frequent: number }

function coverageOf(model: Model, memberId: number): Coverage {
  const byZone = new Map<number | null, { owner: number; backup: number }>();
  let owner = 0;
  let backup = 0;
  let frequent = 0;
  for (const task of model.state.tasks) {
    const isOwner = task.owner === memberId;
    const isBackup = task.fallbacks.some((f) => f.member === memberId);
    if (!isOwner && !isBackup) continue;
    const zid = task.process ? model.process.get(task.process)?.zone ?? null : null;
    const z = byZone.get(zid) ?? { owner: 0, backup: 0 };
    if (isOwner) { z.owner += 1; owner += 1; if (task.frequent) frequent += 1; } else { z.backup += 1; backup += 1; }
    byZone.set(zid, z);
  }
  const zones = [...byZone.entries()]
    .map(([zid, v]) => ({ zone: zid ? model.zone.get(zid) ?? null : null, ...v }))
    .sort((a, b) => b.owner - a.owner || b.backup - a.backup);
  return { zones, owner, backup, frequent };
}

/** Xodimlar: kim qaysi holatda javob beradi — daraja, aniq vazifalar, chegaralar, kimga o'tkazadi, kim nazorat qiladi. */
export function Employees() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const { inScope } = useScope();
  const [query, setQuery] = useState("");
  const [level, setLevel] = useState<MemberLevel | "all">("all");
  const [edit, setEdit] = useState<Member | null | undefined>(undefined);
  const q = norm(query.trim());
  const members = model.memberOrder.filter(inScope);
  const list = members
    .filter((m) => level === "all" || m.level === level)
    .filter((m) => !q || norm(`${m.name} ${m.role} ${m.trigger} ${m.does} ${m.duties.join(" ")} ${m.excludes} ${m.escalation}`).includes(q));
  const leads = members.filter((m) => m.level === "LEAD");

  return (
    <Page>
      <PageHeader
        title={t("people.title")}
        description={t("people.description")}
        actions={can.edit && <Button onClick={() => setEdit(null)}><Plus className="size-4" />{t("forms.member.new")}</Button>}
      />

      {/* murojaat yo'li */}
      <Card className="mb-6 gap-4 p-5">
        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
          <ArrowRight className="size-3.5" />{t("people.flow")}
        </div>
        {!!leads.length && (
          <div className="flex flex-wrap items-center justify-center gap-2 rounded-xl border border-dashed p-2.5" style={{ borderColor: `color-mix(in srgb, ${LEVEL_COLOR.LEAD} 50%, transparent)` }}>
            <span className="flex items-center gap-1.5 text-xs font-semibold" style={{ color: LEVEL_COLOR.LEAD }}><Eye className="size-3.5" />{t("people.levels.LEAD")}</span>
            {leads.map((m) => <PersonChip key={m.id} m={m} />)}
            <span className="text-xs text-muted-foreground">{t("people.leadHint")}</span>
          </div>
        )}
        <div className="flex flex-col gap-2 lg:flex-row lg:items-stretch">
          {FLOW.filter((lv) => members.some((m) => m.level === lv)).map((lv, i, arr) => (
            <div key={lv} className="flex flex-1 flex-col gap-2 lg:flex-row lg:items-center">
              <button
                type="button" onClick={() => setLevel(level === lv ? "all" : lv)}
                className={cn("flex-1 rounded-xl border p-3 text-left transition-colors hover:bg-muted/40", level === lv && "ring-2")}
                style={{ borderTop: `3px solid ${LEVEL_COLOR[lv]}`, ...(level === lv ? { ["--tw-ring-color" as string]: LEVEL_COLOR[lv] } : {}) }}
              >
                <div className="text-xs font-semibold" style={{ color: LEVEL_COLOR[lv] }}>{t(`people.levels.${lv}`)}</div>
                <div className="mb-2 text-[11px] text-muted-foreground">{t(`people.levelHint.${lv}`)}</div>
                <div className="flex flex-wrap gap-1">{members.filter((m) => m.level === lv).map((m) => <PersonChip key={m.id} m={m} />)}</div>
              </button>
              {i < arr.length - 1 && <ArrowRight className="mx-auto size-4 shrink-0 rotate-90 text-muted-foreground lg:rotate-0" />}
            </div>
          ))}
        </div>
      </Card>

      <div className="mb-5 flex flex-wrap items-center gap-2">
        <div className="relative min-w-64 flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("people.search")} className="h-10 pl-9" />
        </div>
        <Button variant={level === "all" ? "default" : "outline"} onClick={() => setLevel("all")}>{t("staff.all")} · {members.length}</Button>
        {LEVELS.filter((lv) => members.some((m) => m.level === lv)).map((lv) => (
          <Button key={lv} variant={level === lv ? "default" : "outline"} onClick={() => setLevel(lv)}>
            <span className="size-2 rounded-full" style={{ background: LEVEL_COLOR[lv] }} />{t(`people.levels.${lv}Short`)}
          </Button>
        ))}
      </div>

      {!list.length && <EmptyState icon={Users} title={t("common.nothingFound")} />}
      <div className="grid gap-4 xl:grid-cols-2">
        {list.map((m) => <PersonCard key={m.id} m={m} model={model} canEdit={can.edit} onEdit={() => setEdit(m)} />)}
      </div>
      <MemberDialog open={edit !== undefined} onOpenChange={(o) => !o && setEdit(undefined)} member={edit ?? undefined} />
    </Page>
  );
}

function PersonChip({ m }: { m: Member }) {
  return (
    <Link href={`/employees/${m.id}`} onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-1.5 rounded-full border bg-card py-0.5 pl-0.5 pr-2 text-xs hover:border-primary/50">
      <MemberAvatar member={m} size={20} />{m.name}
    </Link>
  );
}

function PersonCard({ m, model, canEdit, onEdit }: { m: Member; model: Model; canEdit: boolean; onEdit: () => void }) {
  const t = useTranslations();
  const cov = useMemo(() => coverageOf(model, m.id), [model, m.id]);
  const dept = m.department ? model.dept.get(m.department) : undefined;
  const team = m.team ? model.team.get(m.team) : undefined;
  const boss = m.manager ? model.member.get(m.manager) : undefined;
  const reports = model.reports.get(m.id) ?? [];
  const auth = model.authorities.get(m.id) ?? [];
  const color = m.level ? LEVEL_COLOR[m.level] : "var(--border)";
  return (
    <Card className="gap-0 overflow-hidden p-0" style={{ borderTop: `3px solid ${color}` }}>
      {/* sarlavha */}
      <div className="flex items-start gap-3 px-5 pt-4">
        <MemberAvatar member={m} size={48} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Link href={`/employees/${m.id}`} className="text-base font-semibold hover:text-primary">{m.name}</Link>
            <LevelBadge level={m.level} />
          </div>
          <div className="text-sm text-muted-foreground">{m.role}</div>
          <div className="text-xs text-muted-foreground">{[dept?.name, team?.name].filter(Boolean).join(" / ")}</div>
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <StaffContacts person={{ phone: m.phone, telegram: m.telegram }} compact />
          {canEdit && <Button variant="ghost" size="icon" className="size-8" onClick={onEdit} aria-label={t("common.edit")}><Pencil className="size-4" /></Button>}
        </div>
      </div>

      <div className="space-y-3 px-5 py-4">
        {m.trigger && (
          <div className="rounded-lg px-3 py-2" style={{ background: `color-mix(in srgb, ${color} 10%, transparent)` }}>
            <div className="text-[10.5px] font-semibold uppercase tracking-wider" style={{ color }}>{t("people.when")}</div>
            <div className="text-[13.5px] font-medium">{m.trigger}</div>
          </div>
        )}
        {m.does && <p className="text-[13px] text-muted-foreground">{m.does}</p>}
        {!!m.duties.length && (
          <div>
            <div className="mb-1.5 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">{t("people.duties")}</div>
            <ul className="space-y-1">
              {m.duties.map((d) => (
                <li key={d} className="flex gap-2 text-[13px]"><CircleCheck className="mt-0.5 size-3.5 shrink-0 text-success" />{d}</li>
              ))}
            </ul>
          </div>
        )}
        <div className="grid gap-2 sm:grid-cols-2">
          {m.excludes && (
            <div className="rounded-lg border border-destructive/25 bg-destructive/5 px-3 py-2">
              <div className="mb-0.5 flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wider text-destructive"><Ban className="size-3" />{t("people.notFor")}</div>
              <p className="text-[12.5px]">{m.excludes}</p>
            </div>
          )}
          {m.escalation && (
            <div className="rounded-lg border bg-muted/30 px-3 py-2">
              <div className="mb-0.5 flex items-center gap-1 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground"><ArrowUpRight className="size-3" />{t("people.escalation")}</div>
              <p className="text-[12.5px]">{m.escalation}</p>
            </div>
          )}
        </div>
        {!!auth.length && (
          <div className="flex flex-wrap gap-1.5">
            {auth.map((a) => (
              <span key={a.id} title={a.scope} className="inline-flex items-center gap-1 rounded-full border bg-card px-2 py-0.5 text-[11.5px]">
                <KeyRound className="size-3 text-primary" />{a.title}
              </span>
            ))}
          </div>
        )}
      </div>

      {/* pastki qism: zonalar, savollar, nazorat */}
      <div className="mt-auto space-y-2 border-t bg-muted/20 px-5 py-3">
        {!!cov.zones.length && (
          <div className="flex flex-wrap items-center gap-1.5">
            {cov.zones.map(({ zone, owner, backup }) => (
              <span key={zone?.id ?? "none"} className="inline-flex items-center gap-1.5 rounded-full border bg-card py-0.5 pl-0.5 pr-2 text-[11.5px]" title={t("people.zoneTitle", { owner, backup })}>
                <ZoneIcon zone={zone ?? undefined} size={18} className="rounded-full" />{zone?.name ?? t("knowledge.noZone")}
                <span className="font-mono text-muted-foreground">{owner}{backup ? `+${backup}` : ""}</span>
              </span>
            ))}
          </div>
        )}
        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>{t("people.answers", { owner: cov.owner, backup: cov.backup })}</span>
          {!!cov.frequent && <span className="flex items-center gap-1 text-warning"><Star className="size-3 fill-current" />{t("people.frequent", { count: cov.frequent })}</span>}
          {boss && <span className="flex items-center gap-1"><ShieldCheck className="size-3.5" />{t("people.supervisedBy")}: <PersonChip m={boss} /></span>}
          {!!reports.length && <span className="flex flex-wrap items-center gap-1"><Eye className="size-3.5" />{t("people.supervises")}: {reports.map((r) => <PersonChip key={r.id} m={r} />)}</span>}
          <Link href={`/employees/${m.id}`} className="ml-auto flex items-center gap-1 text-primary hover:underline">360°<ArrowRight className="size-3" /></Link>
        </div>
      </div>
    </Card>
  );
}
