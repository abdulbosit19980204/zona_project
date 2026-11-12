"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Bar, BarChart, CartesianGrid, Legend, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { axisProps, CHART, ChartCard, tooltipStyle } from "@/components/charts/chart-kit";
import { MemberAvatar } from "@/components/common/member-avatar";
import { Page, PageHeader } from "@/components/common/page";
import { Card } from "@/components/ui/card";
import { useModel, useScope } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

/** Ish yuklamasi: vazifalar + rollar og'irligi (ball). O'rtachadan 35% ortig'i — ortiqcha yuklama. */
export function WorkloadView() {
  const t = useTranslations();
  const model = useModel();
  const { inScope } = useScope();
  const list = model.workload.filter((w) => inScope(w.member)).sort((a, b) => b.score - a.score);
  const active = list.filter((w) => w.score > 0);
  const avg = active.reduce((s, w) => s + w.score, 0) / Math.max(1, active.length);
  const max = Math.max(1, ...list.map((w) => w.score));
  const data = list.map((w) => ({
    name: w.member.name, tasks: w.tasks, owned: w.owned * 3, approvals: w.approvals * 3, other: w.other * 3,
  }));

  return (
    <Page>
      <PageHeader title={t("nav.workload")} description={t("workload.description")} />
      <ChartCard title={t("workload.chart")} description={t("workload.chartHint", { avg: avg.toFixed(1) })}>
        <ResponsiveContainer width="100%" height={320}>
          <BarChart data={data} margin={{ left: -16 }}>
            <CartesianGrid vertical={false} stroke={CHART.grid} />
            <XAxis dataKey="name" {...axisProps} interval={0} angle={-20} textAnchor="end" height={60} />
            <YAxis {...axisProps} allowDecimals={false} />
            <Tooltip {...tooltipStyle} />
            <Legend wrapperStyle={{ fontSize: 12 }} />
            <ReferenceLine y={avg * 1.35} stroke={CHART.warning} strokeDasharray="6 4" label={{ value: t("workload.threshold"), fill: CHART.text, fontSize: 11, position: "insideTopRight" }} />
            <Bar dataKey="tasks" name={t("workload.tasks")} stackId="w" fill={CHART.primary} maxBarSize={44} />
            <Bar dataKey="owned" name={t("workload.owned")} stackId="w" fill={CHART.violet} maxBarSize={44} />
            <Bar dataKey="approvals" name={t("workload.approvals")} stackId="w" fill={CHART.cyan} maxBarSize={44} />
            <Bar dataKey="other" name={t("workload.other")} stackId="w" fill={CHART.muted} radius={[4, 4, 0, 0]} maxBarSize={44} />
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <Card className="mt-4 gap-0 p-2">
        {list.map((w) => (
          <Link key={w.member.id} href={`/employees/${w.member.id}`} className="flex items-center gap-3 rounded-lg px-3 py-2.5 hover:bg-muted/60">
            <MemberAvatar member={w.member} size={32} />
            <div className="w-56 min-w-0">
              <div className="truncate text-sm font-medium">{w.member.name}</div>
              <div className="truncate text-xs text-muted-foreground">{w.member.role}</div>
            </div>
            <div className="h-2 flex-1 overflow-hidden rounded-full bg-muted">
              <div className={cn("h-full rounded-full", w.excessive ? "bg-warning" : "bg-primary")} style={{ width: `${(w.score / max) * 100}%` }} />
            </div>
            <div className="hidden w-72 text-right text-xs text-muted-foreground md:block">
              {t("workload.breakdown", { tasks: w.tasks, owned: w.owned, approvals: w.approvals, other: w.other })}
            </div>
            <span className={cn("w-12 text-right font-mono text-sm font-semibold", w.excessive && "text-warning")}>{w.score}</span>
            {w.excessive
              ? <span className="w-24 rounded-md bg-warning/15 px-1.5 py-0.5 text-center text-xs text-warning">{t("workload.excessive")}</span>
              : <span className="w-24" />}
          </Link>
        ))}
      </Card>
    </Page>
  );
}
