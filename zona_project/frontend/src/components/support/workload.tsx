"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Clock3, Gauge, Layers, Timer, Users } from "lucide-react";
import { useState } from "react";

import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import { supportApi, type Workload as W, type WorkloadRow } from "./api";
import { Initials, Metric, Panel } from "./common";
import type { SKey, ST } from "./i18n";

const WD: SKey[] = ["wd0", "wd1", "wd2", "wd3", "wd4", "wd5", "wd6"];
const mins = (t: ST, v: number | null) => (v == null ? "—" : v >= 60 ? t("wlHours", { n: (v / 60).toFixed(1) }) : t("anMin", { n: v }));
/** Ketma-ket (bir rang, ochdan to'qqa) shkala: 0 — bo'sh katak, qolgani asosiy rangning to'yinganligi. */
const shade = (v: number, max: number) => (v ? `color-mix(in oklab, var(--primary) ${Math.round(12 + 88 * (v / max))}%, var(--card))` : undefined);

/** Ish yuklamasi: qachon va qayerdan ko'p savol tushadi, xodimlar qancha tez va qancha vaqt ishlaydi. */
export function Workload({ days, t }: { days: number; t: ST }) {
  const q = useQuery({ queryKey: ["support", "workload", days], queryFn: () => supportApi.workload(days), refetchInterval: 120_000 });
  const d = q.data;
  if (!d) return <Skeleton className="h-96" />;
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label={t("wlHuman")} value={d.answered_by_human} hint={t("wlOf", { n: d.questions })} icon={Users} tone="primary" />
        <Metric label={t("wlMedian")} value={mins(t, d.first_median)} hint={t("wlMedianHint")} icon={Timer} tone="success" />
        <Metric label={t("wlP90")} value={mins(t, d.first_p90)} hint={t("wlP90Hint")} icon={Gauge} tone="warning" />
        <Metric label={t("wlWithin15")} value={d.within_15 == null ? "—" : `${d.within_15}%`} icon={Clock3} />
      </div>

      <div className="grid gap-4 xl:grid-cols-[1fr_340px]">
        <Heatmap d={d} t={t} />
        <Panel title={t("wlBuckets")} hint={t("wlBucketsHint")} icon={Timer}>
          <Buckets d={d} t={t} />
        </Panel>
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("wlWeeks")} icon={CalendarDays} bodyClassName="p-0">
          <Table>
            <TableHeader><TableRow className="bg-muted/40">
              <TableHead className="pl-4">{t("wlWeek")}</TableHead><TableHead className="text-right">{t("anQuestions")}</TableHead>
              <TableHead className="text-right">{t("kpiBot")}</TableHead><TableHead className="text-right">{t("wlHumanShort")}</TableHead>
              <TableHead className="text-right">{t("anUnanswered")}</TableHead><TableHead className="pr-4 text-right">{t("wlMedianShort")}</TableHead>
            </TableRow></TableHeader>
            <TableBody>
              {d.weeks.length === 0 && <TableRow><TableCell colSpan={6} className="pl-4 text-muted-foreground">{t("empty")}</TableCell></TableRow>}
              {[...d.weeks].reverse().map((w) => (
                <TableRow key={w.week}>
                  <TableCell className="pl-4 font-mono text-xs">{w.week}</TableCell>
                  <TableCell className="text-right font-mono">{w.questions}</TableCell>
                  <TableCell className="text-right font-mono">{w.bot}</TableCell>
                  <TableCell className="text-right font-mono">{w.human}</TableCell>
                  <TableCell className="text-right font-mono">{w.unanswered}</TableCell>
                  <TableCell className="pr-4 text-right font-mono text-xs">{mins(t, w.median)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Panel>
        <RowsTable title={t("anGroups")} icon={Users} rows={d.groups.map((g) => ({ ...g, key: g.group }))} t={t} showUnanswered />
      </div>

      <RowsTable title={t("wlTypes")} hint={t("wlTypesHint")} icon={Layers} rows={d.types.map((x) => ({ ...x, key: x.type }))} t={t} />
      <StaffWork d={d} t={t} />
    </div>
  );
}

function Heatmap({ d, t }: { d: W; t: ST }) {
  const [hover, setHover] = useState<{ wd: number; h: number } | null>(null);
  const max = Math.max(1, ...d.heatmap.flat());
  const peakWd = d.by_weekday.indexOf(Math.max(...d.by_weekday));
  return (
    <Panel title={t("wlHeat")} hint={t("wlHeatHint")} icon={CalendarDays}
      actions={<span className="text-xs text-muted-foreground">{d.questions ? t("wlPeakDay", { d: t(WD[peakWd]) }) : ""}</span>}>
      <div className="overflow-x-auto">
        <div className="grid min-w-[560px] gap-[2px]" style={{ gridTemplateColumns: "28px repeat(24, minmax(0, 1fr)) 40px" }}
          onMouseLeave={() => setHover(null)}>
          <span />
          {Array.from({ length: 24 }, (_, h) => <span key={h} className="text-center text-[10px] tabular-nums text-muted-foreground">{h % 3 === 0 ? h : ""}</span>)}
          <span className="text-right text-[10px] text-muted-foreground">Σ</span>
          {d.heatmap.map((row, wd) => (
            <div key={wd} className="contents">
              <span className="self-center text-[11px] text-muted-foreground">{t(WD[wd])}</span>
              {row.map((v, h) => (
                <button key={h} type="button" aria-label={`${t(WD[wd])} ${h}:00 — ${v}`}
                  onMouseEnter={() => setHover({ wd, h })} onFocus={() => setHover({ wd, h })}
                  className={`aspect-square rounded-[3px] outline-none ring-offset-1 ring-offset-card focus-visible:ring-2 focus-visible:ring-ring ${v ? "" : "bg-muted/60"} ${hover?.wd === wd && hover?.h === h ? "ring-2 ring-foreground/60" : ""}`}
                  style={{ background: shade(v, max) }} />
              ))}
              <span className="self-center text-right font-mono text-[11px] tabular-nums">{d.by_weekday[wd]}</span>
            </div>
          ))}
        </div>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        <span className="min-h-4 flex-1">
          {hover ? <><b className="text-foreground">{t(WD[hover.wd])} {String(hover.h).padStart(2, "0")}:00–{String(hover.h + 1).padStart(2, "0")}:00</b> · {t("wlQ", { n: d.heatmap[hover.wd][hover.h] })}</>
            : d.busiest_dates.length > 0 && <>{t("wlBusiest")}: {d.busiest_dates.slice(0, 3).map((x) => `${x.date} (${x.n})`).join(", ")}</>}
        </span>
        <span className="inline-flex items-center gap-1.5">{t("wlFew")}
          <span className="h-2 w-24 rounded-full" style={{ background: "linear-gradient(90deg, color-mix(in oklab, var(--primary) 12%, var(--card)), var(--primary))" }} />
          {t("wlMany")} ({max})</span>
      </div>
    </Panel>
  );
}

function Buckets({ d, t }: { d: W; t: ST }) {
  const max = Math.max(1, ...d.buckets.map((b) => b.n));
  const total = d.buckets.reduce((s, b) => s + b.n, 0);
  return (
    <div className="grid gap-3">
      <div className="flex h-40 items-end gap-2 border-b">
        {d.buckets.map((b) => (
          <div key={b.label} className="group flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${b.label} ${t("min")}: ${b.n}`}>
            <span className="font-mono text-[11px] tabular-nums">{b.n}</span>
            <div className="w-full max-w-10 rounded-t-[4px] bg-primary transition-opacity group-hover:opacity-80" style={{ height: `${(100 * b.n) / max}%`, minHeight: b.n ? 2 : 0 }} />
          </div>
        ))}
      </div>
      <div className="flex gap-2">{d.buckets.map((b) => <span key={b.label} className="flex-1 text-center text-[11px] text-muted-foreground">{b.label}</span>)}</div>
      <p className="text-xs text-muted-foreground">{t("wlBucketsNote", { n: total })}</p>
    </div>
  );
}

function RowsTable({ title, hint, icon, rows, t, showUnanswered }: {
  title: string; hint?: string; icon: typeof Users; rows: (WorkloadRow & { key: string })[]; t: ST; showUnanswered?: boolean;
}) {
  return (
    <Panel title={title} hint={hint} icon={icon} bodyClassName="p-0">
      <Table>
        <TableHeader><TableRow className="bg-muted/40">
          <TableHead className="pl-4">{title}</TableHead><TableHead className="text-right">{t("anQuestions")}</TableHead>
          <TableHead className="text-right">{t("wlBotRate")}</TableHead>
          {showUnanswered && <TableHead className="text-right">{t("anUnanswered")}</TableHead>}
          <TableHead className="text-right">{t("wlMedianShort")}</TableHead><TableHead className="pr-4 text-right">p90</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.length === 0 && <TableRow><TableCell colSpan={6} className="pl-4 text-muted-foreground">{t("empty")}</TableCell></TableRow>}
          {rows.map((r) => (
            <TableRow key={r.key}>
              <TableCell className="max-w-80 truncate pl-4" title={r.key}>{r.key}</TableCell>
              <TableCell className="text-right font-mono">{r.questions}</TableCell>
              <TableCell className="text-right">
                <div className="font-mono text-xs">{r.bot_rate}%</div>
                <div className="ml-auto mt-1 h-1 w-14 rounded-full bg-muted"><div className="h-1 rounded-full bg-primary" style={{ width: `${r.bot_rate}%` }} /></div>
              </TableCell>
              {showUnanswered && <TableCell className="text-right font-mono">{r.unanswered ?? 0}</TableCell>}
              <TableCell className="text-right font-mono text-xs">{mins(t, r.median)}</TableCell>
              <TableCell className="pr-4 text-right font-mono text-xs">{mins(t, r.p90)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Panel>
  );
}

function StaffWork({ d, t }: { d: W; t: ST }) {
  return (
    <Panel title={t("wlStaff")} hint={t("wlStaffHint")} icon={Users} bodyClassName="p-0">
      <Table>
        <TableHeader><TableRow className="bg-muted/40">
          <TableHead className="pl-4">{t("staff")}</TableHead>
          <TableHead className="text-right">{t("anAnswers")}</TableHead>
          <TableHead className="text-right">{t("anPerDay")} / {t("wlPerWeek")}</TableHead>
          <TableHead className="text-right">{t("wlActiveHours")}</TableHead>
          <TableHead className="text-right">{t("wlFirst")}</TableHead>
          <TableHead className="text-right">{t("wlWithin15")}</TableHead>
          <TableHead className="pr-4">{t("wlHoursCol")}</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {d.staff.length === 0 && <TableRow><TableCell colSpan={7} className="pl-4 text-muted-foreground">{t("empty")}</TableCell></TableRow>}
          {d.staff.map((s) => {
            const max = Math.max(1, ...s.hours);
            return (
              <TableRow key={s.name}>
                <TableCell className="pl-4">
                  <div className="flex items-center gap-2.5">
                    <Initials name={s.name} className="size-8" />
                    <div>
                      <div className="font-medium">{s.name}</div>
                      <div className="text-[11px] text-muted-foreground">{t("anDays", { n: s.active_days })}{s.peak_hour != null && ` · ${t("wlPeakHour", { h: s.peak_hour })}`}</div>
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-right font-mono">{s.answers}{s.clarifications > 0 && <span className="text-xs text-muted-foreground"> +{s.clarifications}</span>}</TableCell>
                <TableCell className="text-right font-mono text-xs">{s.per_day} / {s.per_week}</TableCell>
                <TableCell className="text-right font-mono text-xs">{t("wlHours", { n: s.active_hours_avg })}</TableCell>
                <TableCell className="text-right font-mono text-xs">{mins(t, s.first_median)}
                  {s.first_p90 != null && <div className="text-muted-foreground">p90 {mins(t, s.first_p90)}</div>}</TableCell>
                <TableCell className="text-right font-mono text-xs">{s.within_15 == null ? "—" : `${s.within_15}%`}</TableCell>
                <TableCell className="pr-4">
                  <div className="flex h-6 w-40 items-end gap-px" aria-label={t("wlHoursCol")}>
                    {s.hours.map((v, h) => (
                      <span key={h} title={`${h}:00 — ${v}`} className="flex-1 rounded-t-[1px] bg-primary/80"
                        style={{ height: `${(100 * v) / max}%`, minHeight: v ? 2 : 1, opacity: v ? 1 : 0.15 }} />
                    ))}
                  </div>
                  <div className="flex w-40 justify-between text-[9px] text-muted-foreground"><span>0</span><span>12</span><span>23</span></div>
                </TableCell>
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </Panel>
  );
}
