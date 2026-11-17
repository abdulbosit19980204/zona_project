"use client";

import { CheckCircle2, Clock, Download, FileStack, HardDrive, Timer, TriangleAlert, Users } from "lucide-react";
import { useState } from "react";
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

import { axisProps, CHART, SERIES, tooltipStyle } from "@/components/charts/chart-kit";
import { Page, PageHeader, StatCard } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useQr } from "@/hooks/use-qrdrive";
import { download, formatBytes } from "@/lib/api/qrdrive";

import { QrGuard, useDuration } from "./common";
import { errorText, useQt, type QKey } from "./i18n";

interface Named { name: string; count: number; size: number }
interface Analytics {
  range: { from: string; to: string };
  totals: { delivered: number; failed: number; size: number; employees: number; success_rate: number | null; avg_ms: number | null; saved_minutes: number };
  daily: { date: string; delivered: number; failed: number; size: number }[];
  employees: Named[]; departments: Named[]; storages: Named[];
  types: { type: string; count: number }[]; sizes: { bucket: string; count: number }[];
  heatmap: number[][]; sources: { source: string; count: number }[];
  errors: { kind: string; title: string; hint: string; count: number }[];
  stages: { stage: string; avg_ms: number | null }[];
  api_keys: { name: string; requests: number; avg_ms: number; errors: number }[];
}

function iso(d: Date) {
  return d.toISOString().slice(0, 10);
}

/** Oxirgi N kun (bugun bilan): [boshlanish, tugash] */
function lastDays(days: number): [string, string] {
  const end = new Date();
  const start = new Date(end);
  start.setDate(end.getDate() - days + 1);
  return [iso(start), iso(end)];
}

function ChartCard({ title, children, className }: { title: string; children: React.ReactNode; className?: string }) {
  return (
    <Card className={`gap-0 p-5 ${className ?? ""}`}>
      <div className="mb-3 text-sm font-medium">{title}</div>
      {children}
    </Card>
  );
}

function Ranking({ rows, unit }: { rows: Named[]; unit: string }) {
  const max = Math.max(1, ...rows.map((r) => r.count));
  return (
    <div className="grid gap-2">
      {rows.map((r) => (
        <div key={r.name} className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-x-3 text-sm">
          <span className="truncate">{r.name}</span>
          <span className="font-mono text-xs text-muted-foreground">{r.count} · {formatBytes(r.size)}</span>
          <div className="col-span-2 h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full rounded-full bg-primary" style={{ width: `${(r.count / max) * 100}%` }} />
          </div>
        </div>
      ))}
      {!rows.length && <p className="text-sm text-muted-foreground">{unit}</p>}
    </div>
  );
}

/** Analitika: sana oralig'i, grafiklar, reytinglar, faollik xaritasi, Excel eksport. */
export function QrAnalytics() {
  const t = useQt();
  const dur = useDuration();
  const [from, setFrom] = useState(() => lastDays(30)[0]);
  const [to, setTo] = useState(() => lastDays(30)[1]);
  const params = { date_from: from, date_to: to };
  const q = useQr<Analytics>(["analytics"], "analytics", params);
  const d = q.data;
  const preset = (days: number) => {
    const [a, b] = lastDays(days);
    setFrom(a);
    setTo(b);
  };
  const weekdays = t("weekdays").split(",");
  const heatMax = d ? Math.max(1, ...d.heatmap.flat()) : 1;

  return (
    <Page>
      <PageHeader title={t("anTitle")} description={t("anDesc")} actions={
        <>
          <div className="flex items-center gap-1">
            {[7, 30, 90].map((n) => <Button key={n} size="sm" variant="ghost" onClick={() => preset(n)}>{t(`days${n}` as QKey)}</Button>)}
          </div>
          <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40" aria-label={t("dateFrom")} />
          <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" aria-label={t("dateTo")} />
          <Button variant="outline" onClick={() => download("analytics/export.xlsx", "qrdrive-analitika.xlsx", params)}><Download className="size-4" />{t("anExport")}</Button>
        </>
      } />
      <QrGuard query={q}>
        {d && (
          <>
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-6">
              <StatCard label={t("st_delivered")} value={d.totals.delivered} icon={FileStack} />
              <StatCard label={t("st_failed")} value={d.totals.failed} icon={TriangleAlert} tone={d.totals.failed ? "warning" : "default"} />
              <StatCard label={t("kpiSize")} value={formatBytes(d.totals.size)} icon={HardDrive} />
              <StatCard label={t("kpiActive")} value={d.totals.employees} icon={Users} />
              <StatCard label={t("kpiSuccess")} icon={CheckCircle2} value={d.totals.success_rate === null ? "—" : `${Math.round(d.totals.success_rate * 100)}%`} />
              <StatCard label={t("kpiAvg")} value={dur(d.totals.avg_ms)} icon={Timer}
                hint={`${t("kpiSaved")}: ${d.totals.saved_minutes >= 60 ? t("hours", { n: Math.round(d.totals.saved_minutes / 60) }) : t("minutes", { n: d.totals.saved_minutes })}`} />
            </div>

            <div className="mt-4 grid gap-4 xl:grid-cols-3">
              <ChartCard title={t("anDaily")} className="xl:col-span-2">
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <AreaChart data={d.daily} margin={{ left: -20, right: 4 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} strokeDasharray="3 3" />
                      <XAxis dataKey="date" {...axisProps} tickFormatter={(v: string) => `${v.slice(8, 10)}.${v.slice(5, 7)}`} minTickGap={16} />
                      <YAxis {...axisProps} allowDecimals={false} />
                      <Tooltip {...tooltipStyle} />
                      <Area type="monotone" dataKey="delivered" name={t("st_delivered")} stroke={CHART.primary} fill={CHART.primary} fillOpacity={0.15} />
                      <Area type="monotone" dataKey="failed" name={t("st_failed")} stroke="var(--destructive)" fill="var(--destructive)" fillOpacity={0.1} />
                    </AreaChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>
              <ChartCard title={t("anTypes")}>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <PieChart>
                      <Pie data={d.types.map((x) => ({ ...x, label: t(`ft_${x.type}` as QKey) }))} dataKey="count" nameKey="label"
                        innerRadius="55%" outerRadius="85%" paddingAngle={2}>
                        {d.types.map((x, i) => <Cell key={x.type} fill={SERIES[i % SERIES.length]} />)}
                      </Pie>
                      <Tooltip {...tooltipStyle} />
                    </PieChart>
                  </ResponsiveContainer>
                </div>
                <div className="flex flex-wrap gap-x-3 gap-y-1 text-xs">
                  {d.types.map((x, i) => (
                    <span key={x.type} className="flex items-center gap-1.5"><span className="size-2 rounded-full" style={{ background: SERIES[i % SERIES.length] }} />
                      {t(`ft_${x.type}` as QKey)} · {x.count}</span>
                  ))}
                </div>
              </ChartCard>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2 xl:grid-cols-3">
              <ChartCard title={t("anEmployees")}><Ranking rows={d.employees} unit={t("emptyHint")} /></ChartCard>
              <ChartCard title={t("anDepartments")}><Ranking rows={d.departments} unit={t("emptyHint")} /></ChartCard>
              <ChartCard title={t("anSizes")}>
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.sizes} margin={{ left: -20, right: 4 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} strokeDasharray="3 3" />
                      <XAxis dataKey="bucket" {...axisProps} />
                      <YAxis {...axisProps} allowDecimals={false} />
                      <Tooltip {...tooltipStyle} />
                      <Bar dataKey="count" name={t("anFiles")} fill={CHART.violet} radius={[4, 4, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>
            </div>

            <ChartCard title={t("anHeat")} className="mt-4">
              <div className="overflow-x-auto">
                <div className="grid min-w-[640px] grid-cols-[32px_repeat(24,minmax(0,1fr))] gap-[3px] text-[10px] text-muted-foreground">
                  <span />
                  {Array.from({ length: 24 }, (_, h) => <span key={h} className="text-center">{h}</span>)}
                  {d.heatmap.map((row, w) => (
                    <div key={w} className="contents">
                      <span className="self-center">{weekdays[w]}</span>
                      {row.map((n, h) => (
                        <span key={h} title={`${weekdays[w]} ${h}:00 — ${n}`} className="aspect-square rounded-[3px]"
                          style={{ background: n ? `color-mix(in srgb, var(--primary) ${Math.round(15 + (n / heatMax) * 85)}%, transparent)` : "var(--muted)" }} />
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            </ChartCard>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <ChartCard title={t("anStages")}>
                <div className="h-56">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.stages.map((x) => ({ ...x, label: t(`stage_${x.stage}` as QKey), sec: x.avg_ms === null ? 0 : x.avg_ms / 1000 }))}
                      layout="vertical" margin={{ left: 40, right: 16 }}>
                      <CartesianGrid horizontal={false} stroke={CHART.grid} strokeDasharray="3 3" />
                      <XAxis type="number" {...axisProps} unit=" s" />
                      <YAxis type="category" dataKey="label" {...axisProps} width={120} />
                      <Tooltip {...tooltipStyle} formatter={(v) => `${Number(v).toFixed(2)} s`} />
                      <Bar dataKey="sec" fill={CHART.cyan} radius={[0, 4, 4, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </ChartCard>
              <ChartCard title={t("anErrors")}>
                {!d.errors.length && <p className="text-sm text-muted-foreground">{t("errEmpty")}</p>}
                <div className="grid gap-2">
                  {d.errors.map((e) => (
                    <div key={e.kind} className="flex items-center gap-3 text-sm">
                      <TriangleAlert className="size-4 shrink-0 text-destructive" />
                      <span className="flex-1">{errorText(t, e)?.title}</span>
                      <span className="font-mono">{e.count}</span>
                    </div>
                  ))}
                </div>
              </ChartCard>
            </div>

            <div className="mt-4 grid gap-4 lg:grid-cols-2">
              <ChartCard title={t("anStorages")}>
                <Table>
                  <TableHeader><TableRow><TableHead>{t("stoName")}</TableHead><TableHead className="text-right">{t("anFiles")}</TableHead><TableHead className="text-right">{t("colSize")}</TableHead></TableRow></TableHeader>
                  <TableBody>{d.storages.map((s) => (
                    <TableRow key={s.name}><TableCell>{s.name}</TableCell><TableCell className="text-right font-mono">{s.count}</TableCell>
                      <TableCell className="text-right font-mono">{formatBytes(s.size)}</TableCell></TableRow>))}</TableBody>
                </Table>
              </ChartCard>
              <ChartCard title={t("anApi")}>
                <Table>
                  <TableHeader><TableRow><TableHead>{t("keyName")}</TableHead><TableHead className="text-right">{t("anRequests")}</TableHead>
                    <TableHead className="text-right">ms</TableHead><TableHead className="text-right">{t("anErrorsN")}</TableHead></TableRow></TableHeader>
                  <TableBody>{d.api_keys.map((k) => (
                    <TableRow key={k.name}><TableCell>{k.name}</TableCell><TableCell className="text-right font-mono">{k.requests}</TableCell>
                      <TableCell className="text-right font-mono">{k.avg_ms}</TableCell><TableCell className="text-right font-mono">{k.errors}</TableCell></TableRow>))}</TableBody>
                </Table>
                {!d.api_keys.length && <p className="mt-2 text-sm text-muted-foreground"><Clock className="mr-1 inline size-3.5" />{t("emptyHint")}</p>}
              </ChartCard>
            </div>
          </>
        )}
      </QrGuard>
    </Page>
  );
}
