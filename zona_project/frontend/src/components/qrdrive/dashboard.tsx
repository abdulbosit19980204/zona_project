"use client";

import {
  AlertTriangle, CalendarDays, CheckCircle2, Clock, FileStack, Gauge, HardDrive, Hourglass, ListOrdered, Timer, Users, Wand2,
} from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { axisProps, CHART, tooltipStyle } from "@/components/charts/chart-kit";
import { Page, PageHeader, SectionTitle, StatCard } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { useQr } from "@/hooks/use-qrdrive";
import { formatBytes, type Dashboard as DashboardData } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { Dot, QrGuard, useDuration } from "./common";
import { useQt } from "./i18n";

export function QrDashboard() {
  const t = useQt();
  const dur = useDuration();
  const q = useQr<DashboardData>(["dashboard"], "dashboard", undefined, { refetchInterval: 30_000 });
  const d = q.data;
  const a = d?.attention;
  const alerts: { text: string; href: string; tone: "warning" | "danger" }[] = [];
  if (a) {
    if (a.no_storage) alerts.push({ text: t("attNoStorage"), href: "/qr/storages", tone: "danger" });
    a.storages_down.forEach((name) => alerts.push({ text: t("attDown", { name }), href: "/qr/storages", tone: "danger" }));
    if (a.worker_down) alerts.push({ text: t("attWorker"), href: "/qr/system", tone: "danger" });
    if (a.bot_down) alerts.push({ text: t("attBot"), href: "/qr/system", tone: "danger" });
    if (a.failed_files) alerts.push({ text: t("attFailed", { n: a.failed_files }), href: "/qr/errors", tone: "danger" });
    if (a.pending_requests) alerts.push({ text: t("attRequests", { n: a.pending_requests }), href: "/qr/requests", tone: "warning" });
    a.quota_high.forEach((name) => alerts.push({ text: t("attQuota", { name }), href: "/qr/storages", tone: "warning" }));
    if (a.links_expiring) alerts.push({ text: t("attExpiring", { n: a.links_expiring }), href: "/qr/files", tone: "warning" });
  }
  const saved = d ? d.kpi.saved_minutes : 0;

  return (
    <Page>
      <PageHeader title={t("dashTitle")} description={t("dashDesc")} />
      <QrGuard query={q} skeleton={<div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="h-28" />)}</div>}>
        {d && (
          <>
            {!d.setup_done && (
              <Card className="mb-5 flex flex-row items-center gap-4 border-primary/30 bg-primary/5 px-5 py-4">
                <Wand2 className="size-6 shrink-0 text-primary" />
                <div className="min-w-0 flex-1">
                  <div className="font-medium">{t("setupCta")}</div>
                  <div className="text-sm text-muted-foreground">{t("setupCtaHint")}</div>
                </div>
                <Button asChild><Link href="/qr/setup">{t("setupOpen")}</Link></Button>
              </Card>
            )}
            <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
              <StatCard label={t("kpiToday")} value={d.kpi.today} icon={CalendarDays} />
              <StatCard label={t("kpiWeek")} value={d.kpi.week} icon={FileStack} />
              <StatCard label={t("kpiMonth")} value={d.kpi.month} icon={ListOrdered} />
              <StatCard label={t("kpiSize")} value={formatBytes(d.kpi.total_size)} icon={HardDrive} hint={t("filesN", { n: d.kpi.total })} />
              <StatCard label={t("kpiActive")} value={d.kpi.active_employees} icon={Users} />
              <StatCard label={t("kpiSuccess")} icon={CheckCircle2}
                value={d.kpi.success_rate === null ? "—" : `${Math.round(d.kpi.success_rate * 100)}%`}
                tone={d.kpi.success_rate !== null && d.kpi.success_rate < 0.9 ? "warning" : "success"}
                progress={d.kpi.success_rate ?? undefined} />
              <StatCard label={t("kpiAvg")} value={dur(d.kpi.avg_ms)} icon={Timer} />
              <StatCard label={t("kpiSaved")} icon={Clock}
                value={saved >= 60 ? t("hours", { n: Math.round(saved / 60) }) : t("minutes", { n: saved })}
                hint={d.kpi.queue ? `${t("kpiQueue")}: ${d.kpi.queue}` : undefined} />
            </div>

            <div className="mt-6 grid gap-4 xl:grid-cols-3">
              <Card className="gap-0 p-5 xl:col-span-2">
                <div className="mb-3 text-sm font-medium">{t("chartDaily")}</div>
                <div className="h-64">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.daily} margin={{ left: -20, right: 4 }}>
                      <CartesianGrid vertical={false} stroke={CHART.grid} strokeDasharray="3 3" />
                      <XAxis dataKey="date" {...axisProps} tickFormatter={(v: string) => v.slice(8, 10) + "." + v.slice(5, 7)} minTickGap={16} />
                      <YAxis {...axisProps} allowDecimals={false} />
                      <Tooltip {...tooltipStyle} />
                      <Bar dataKey="delivered" name={t("st_delivered")} stackId="a" fill={CHART.success} radius={[0, 0, 0, 0]} />
                      <Bar dataKey="failed" name={t("st_failed")} stackId="a" fill="var(--destructive)" radius={[3, 3, 0, 0]} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
              <Card className="gap-0 p-5">
                <div className="mb-3 flex items-center gap-2 text-sm font-medium"><AlertTriangle className="size-4 text-warning" />{t("attention")}</div>
                {!alerts.length && <p className="text-sm text-muted-foreground">{t("allGood")}</p>}
                <div className="grid gap-2">
                  {alerts.map((al, i) => (
                    <Link key={i} href={al.href}
                      className={cn("rounded-lg border px-3 py-2 text-sm hover:bg-muted",
                        al.tone === "danger" ? "border-destructive/30 text-destructive" : "border-warning/30 text-warning")}>
                      {al.text}
                    </Link>
                  ))}
                </div>
              </Card>
            </div>

            <SectionTitle>{t("chartStorages")}</SectionTitle>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {d.storages.map((s) => {
                const pct = s.total && s.used !== null ? s.used / s.total : null;
                return (
                  <Card key={s.id} className="gap-0 px-5 py-4">
                    <div className="flex items-center gap-2 text-sm font-medium">
                      <Dot ok={s.status === "ok"} unknown={s.status === "unknown"} />{s.name}
                      {s.is_primary && <span className="ml-auto text-[11px] text-primary">{t("primary")}</span>}
                    </div>
                    <div className="mt-2 flex items-center gap-2 text-xs text-muted-foreground">
                      <Gauge className="size-3.5" />
                      {pct === null ? "—" : `${formatBytes(s.used)} / ${formatBytes(s.total)} (${Math.round(pct * 100)}%)`}
                    </div>
                    {pct !== null && (
                      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-muted">
                        <div className={cn("h-full rounded-full", pct > 0.9 ? "bg-destructive" : pct > 0.75 ? "bg-warning" : "bg-primary")}
                          style={{ width: `${Math.round(pct * 100)}%` }} />
                      </div>
                    )}
                  </Card>
                );
              })}
              {!d.storages.length && (
                <Card className="flex flex-row items-center gap-3 px-5 py-4 text-sm text-muted-foreground">
                  <Hourglass className="size-4" />{t("stoEmpty")}
                  <Button asChild size="sm" variant="outline" className="ml-auto"><Link href="/qr/storages">{t("addStorage")}</Link></Button>
                </Card>
              )}
            </div>
          </>
        )}
      </QrGuard>
    </Page>
  );
}
