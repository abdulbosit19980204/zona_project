"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, ChevronDown, ChevronRight, Clock, Gauge, Lightbulb, Loader2, Sparkles, Target, Users, Wand2 } from "lucide-react";
import Link from "next/link";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";
import { Bar, CartesianGrid, ComposedChart, Legend, ResponsiveContainer, Scatter, Tooltip, XAxis, YAxis } from "recharts";
import { toast } from "sonner";

import { axisProps, CHART, ChartCard, tooltipStyle } from "@/components/charts/chart-kit";
import { MemberAvatar } from "@/components/common/member-avatar";
import { EmptyState, Page, PageHeader, StatCard } from "@/components/common/page";
import { LoadBar, STATUS_COLOR, TimeChip } from "@/components/common/time";
import { ZoneIcon } from "@/components/common/zone-icon";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { LevelBadge } from "@/components/views/employees";
import { queryKeys, useCan, useModel, useScope } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { aiApi } from "@/lib/api/endpoints";
import type { AIWorkload } from "@/lib/api/types";
import { fmtHours, weekMinutes, type Model, type TimeLoad } from "@/lib/model";
import { cn } from "@/lib/utils";

/**
 * Ish yuklamasi — VAQT bo'yicha: har bir savol turi qancha vaqt oladi × haftasiga necha marta tushadi.
 * Kim sig'imidan ortiq band, qaysi savollar ko'p vaqt oladi, kimga o'tkazish mumkin — qoida va AI tavsiyalari.
 */
export function WorkloadView() {
  const t = useTranslations();
  const locale = useLocale();
  const model = useModel();
  const can = useCan();
  const qc = useQueryClient();
  const { inScope } = useScope();
  const list = [...model.timeLoad.values()].filter((v) => inScope(v.member)).sort((a, b) => b.util - a.util);
  const capacity = list.reduce((s, v) => s + v.capacity, 0);
  const hours = list.reduce((s, v) => s + v.hours, 0);
  const over = list.filter((v) => v.status === "over");
  const tasks = model.state.tasks;
  const guessed = tasks.filter((x) => x.time_source !== "manual").length;
  const refresh = () => qc.invalidateQueries({ queryKey: queryKeys.state });

  const ai = useMutation({ mutationFn: () => aiApi.workload(locale) });
  const estimate = useMutation({
    mutationFn: aiApi.estimate,
    onSuccess: async (r) => { await refresh(); toast.success(t("time.estimated", { count: r.updated })); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const rules = useMutation({
    mutationFn: aiApi.estimateRules,
    onSuccess: async (r) => { await refresh(); toast.success(t("time.estimated", { count: r.updated })); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const aiOn = model.state.meta.ai.workload;

  const data = list.map((v) => ({
    name: v.member.name, owner: +(v.ownerMin / 60).toFixed(1), backup: +(v.backupMin / 60).toFixed(1), capacity: v.capacity,
  }));

  return (
    <Page>
      <PageHeader
        title={t("nav.workload")}
        description={t("time.workloadDescription")}
        actions={(
          <>
            {can.edit && (
              <Button variant="outline" disabled={!aiOn || estimate.isPending} onClick={() => estimate.mutate()} title={aiOn ? undefined : t("ask.aiOff")}>
                {estimate.isPending ? <Loader2 className="size-4 animate-spin" /> : <Wand2 className="size-4" />}{t("time.aiEstimate")}
              </Button>
            )}
            <Button disabled={!aiOn || ai.isPending} onClick={() => ai.mutate()} title={aiOn ? undefined : t("ask.aiOff")}>
              {ai.isPending ? <Loader2 className="size-4 animate-spin" /> : <Sparkles className="size-4" />}{t("time.aiAnalyze")}
            </Button>
          </>
        )}
      />

      {!model.hasTime ? (
        <EmptyState
          icon={Clock} title={t("time.noData")} hint={t("time.noDataHint")}
          action={can.edit ? <Button onClick={() => rules.mutate()} disabled={rules.isPending}><Wand2 className="size-4" />{t("time.ruleEstimate")}</Button> : undefined}
        />
      ) : (
        <>
          <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
            <StatCard label={t("time.totalWeek")} value={`${fmtHours(hours)} ${t("time.h")}`} icon={Clock} />
            <StatCard label={t("time.totalCapacity")} value={`${fmtHours(capacity)} ${t("time.h")}`} icon={Users} />
            <StatCard label={t("time.avgUtil")} value={`${Math.round((hours / Math.max(capacity, 1)) * 100)}%`} icon={Gauge} progress={hours / Math.max(capacity, 1)} />
            <StatCard label={t("time.overloaded")} value={over.length} icon={AlertTriangle} tone={over.length ? "warning" : "default"} />
          </div>
          {!aiOn && (
            <Alert className="mb-4"><AlertDescription>{t("time.aiHint")} <Link href="/settings?tab=ai" className="font-medium text-primary underline">{t("time.aiSettings")}</Link></AlertDescription></Alert>
          )}
          {guessed > 0 && (
            <p className="mb-4 text-xs text-muted-foreground">{t("time.guessedHint", { guessed, total: tasks.length })}</p>
          )}

          {ai.isError && <Alert variant="destructive" className="mb-4"><AlertDescription>{errorMessage(ai.error)}</AlertDescription></Alert>}
          {ai.data && <AiResult result={ai.data} model={model} />}

          <ChartCard title={t("time.chart")} description={t("time.chartHint")}>
            <ResponsiveContainer width="100%" height={320}>
              <ComposedChart data={data} margin={{ left: -12 }}>
                <CartesianGrid vertical={false} stroke={CHART.grid} />
                <XAxis dataKey="name" {...axisProps} interval={0} angle={-20} textAnchor="end" height={60} />
                <YAxis {...axisProps} unit={` ${t("time.h")}`} />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="owner" name={t("time.ownerH")} stackId="h" fill={CHART.primary} maxBarSize={46} />
                <Bar dataKey="backup" name={t("time.backupH")} stackId="h" fill={CHART.violet} radius={[4, 4, 0, 0]} maxBarSize={46} />
                <Scatter dataKey="capacity" name={t("time.capacity")} fill={CHART.warning} shape="diamond" />
              </ComposedChart>
            </ResponsiveContainer>
          </ChartCard>

          <div className="mt-4 grid gap-4 xl:grid-cols-[1.4fr_1fr]">
            <Card className="gap-0 p-2">
              {list.map((v) => <MemberRow key={v.member.id} v={v} model={model} />)}
            </Card>
            <RuleRecommendations model={model} />
          </div>
        </>
      )}
    </Page>
  );
}

function MemberRow({ v, model }: { v: TimeLoad; model: Model }) {
  const t = useTranslations();
  const [open, setOpen] = useState(false);
  const top = [...v.tasks].sort((a, b) => weekMinutes(b) - weekMinutes(a)).slice(0, 6);
  const zones = [...v.zones.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3);
  return (
    <div className="rounded-lg px-3 py-2.5 hover:bg-muted/40">
      <div className="flex items-center gap-3">
        <button type="button" onClick={() => setOpen((x) => !x)} className="text-muted-foreground" aria-label="toggle">
          {open ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </button>
        <MemberAvatar member={v.member} size={34} />
        <div className="w-44 min-w-0">
          <Link href={`/employees/${v.member.id}`} className="flex items-center gap-1.5 truncate text-sm font-medium hover:text-primary">{v.member.name}<LevelBadge level={v.member.level} /></Link>
          <div className="truncate text-xs text-muted-foreground">{v.member.role}</div>
        </div>
        <div className="min-w-0 flex-1"><LoadBar load={v} /></div>
        <span className="w-24 rounded-md px-1.5 py-0.5 text-center text-xs font-medium"
          style={{ color: STATUS_COLOR[v.status], background: `color-mix(in srgb, ${STATUS_COLOR[v.status]} 14%, transparent)` }}>
          {t(`time.status.${v.status}`)}
        </span>
      </div>
      {open && (
        <div className="ml-12 mt-2 space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {zones.map(([zid, min]) => {
              const z = zid ? model.zone.get(zid) : undefined;
              return (
                <span key={zid ?? "none"} className="inline-flex items-center gap-1.5 rounded-full border bg-card py-0.5 pl-0.5 pr-2 text-[11.5px]">
                  <ZoneIcon zone={z} size={18} className="rounded-full" />{z?.name ?? t("knowledge.noZone")}<span className="font-mono text-muted-foreground">{fmtHours(min / 60)} {t("time.h")}</span>
                </span>
              );
            })}
          </div>
          <div className="space-y-1">
            {top.map((task) => (
              <div key={task.id} className="flex items-center gap-2 text-[12.5px]">
                <span className="min-w-0 flex-1 truncate">{task.title}</span>
                <TimeChip task={task} />
                <span className="w-16 text-right font-mono text-xs">{fmtHours(weekMinutes(task) / 60)} {t("time.h")}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Qoidaga asoslangan tavsiyalar (darhol, AI'siz). */
function RuleRecommendations({ model }: { model: Model }) {
  const t = useTranslations();
  const recs = model.recommendations;
  const name = (id?: number) => (id ? model.member.get(id)?.name ?? "?" : "?");
  return (
    <Card className="gap-3 p-4">
      <div className="flex items-center gap-2 font-semibold"><Lightbulb className="size-4 text-warning" />{t("time.recsTitle")}</div>
      <p className="text-xs text-muted-foreground">{t("time.recsHint")}</p>
      {!recs.length && <p className="text-sm text-success">{t("time.noRecs")}</p>}
      <div className="space-y-2">
        {recs.map((r, i) => r.kind === "reassign" ? (
          <div key={i} className="rounded-lg border bg-card px-3 py-2">
            <div className="text-[13px] font-medium">{r.task?.title}</div>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
              <span className="rounded-full border px-2 py-0.5">{name(r.from)}</span><ArrowRight className="size-3" />
              <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary">{name(r.to)}</span>
              <span className="ml-auto font-mono text-success">−{r.hours} {t("time.hPerWeek")}</span>
            </div>
          </div>
        ) : (
          <div key={i} className="rounded-lg border border-warning/40 bg-warning/5 px-3 py-2 text-[13px]">
            <b>{name(r.from)}</b>: {t("time.recCapacity", { hours: r.hours })}
          </div>
        ))}
      </div>
    </Card>
  );
}

const PRIORITY = { high: "var(--destructive)", medium: "var(--warning)", low: "var(--muted-foreground)" } as const;

function AiResult({ result, model }: { result: AIWorkload; model: Model }) {
  const t = useTranslations();
  const name = (id?: number | null) => (id ? model.member.get(id)?.name ?? "?" : "");
  return (
    <Card className="mb-4 gap-4 border-primary/40 p-5">
      <div className="flex items-center gap-2 font-semibold"><Sparkles className="size-4 text-primary" />{t("time.aiTitle")}
        <span className="ml-auto text-xs font-normal text-muted-foreground">{result.meta.model} · {result.meta.latency_ms} ms</span>
      </div>
      <p className="text-sm leading-relaxed">{result.summary}</p>
      {!!result.overloaded.length && (
        <div className="space-y-1">
          {result.overloaded.map((o) => (
            <div key={o.member_id} className="flex gap-2 text-[13px]"><AlertTriangle className="mt-0.5 size-3.5 shrink-0 text-destructive" /><span><b>{name(o.member_id)}</b> — {o.reason}</span></div>
          ))}
        </div>
      )}
      <div className="grid gap-2 lg:grid-cols-2">
        {result.recommendations.map((r, i) => (
          <div key={i} className="rounded-lg border bg-card px-3 py-2" style={{ borderLeft: `3px solid ${PRIORITY[r.priority] ?? PRIORITY.low}` }}>
            <div className="flex items-center gap-2 text-[13px] font-medium">
              <Badge variant="outline" className="text-[10px]">{t(`time.kind.${r.kind}`)}</Badge>{r.title}
            </div>
            <p className="mt-1 text-xs text-muted-foreground">{r.detail}</p>
            <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
              {r.from_id && <span className="rounded-full border px-2 py-0.5">{name(r.from_id)}</span>}
              {r.from_id && r.to_id && <ArrowRight className="size-3 text-muted-foreground" />}
              {r.to_id && <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary">{name(r.to_id)}</span>}
              {!!r.hours_per_week && <span className="ml-auto font-mono text-success">−{r.hours_per_week} {t("time.hPerWeek")}</span>}
            </div>
            {!!r.task_ids?.length && (
              <div className="mt-1 text-[11.5px] text-muted-foreground">{r.task_ids.map((id) => model.task.get(id)?.title).filter(Boolean).join(" · ")}</div>
            )}
          </div>
        ))}
      </div>
      {!!result.best_fit.length && (
        <div>
          <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground"><Target className="size-3.5" />{t("time.bestFit")}</div>
          <div className="grid gap-1.5 md:grid-cols-2">
            {result.best_fit.map((b, i) => (
              <div key={i} className="text-[12.5px]"><b>{b.zone}</b> → <span className="text-primary">{name(b.member_id)}</span> <span className="text-muted-foreground">— {b.why}</span></div>
            ))}
          </div>
        </div>
      )}
      {!!result.risks.length && (
        <ul className={cn("list-disc space-y-0.5 pl-5 text-[12.5px] text-muted-foreground")}>{result.risks.map((r) => <li key={r}>{r}</li>)}</ul>
      )}
    </Card>
  );
}
