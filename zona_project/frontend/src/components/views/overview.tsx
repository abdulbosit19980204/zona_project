"use client";

import {
  AlertTriangle, BadgeCheck, Building2, CircleDot, Copy, Gauge, ListChecks, Network, ShieldAlert, Users, Workflow,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { Bar, BarChart, Cell, Pie, PieChart, PolarAngleAxis, RadialBar, RadialBarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { ActivityItem } from "@/components/common/activity";
import { Page, PageHeader, StatCard } from "@/components/common/page";
import { axisProps, CHART, ChartCard, SERIES, tooltipStyle } from "@/components/charts/chart-kit";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useEvents, useModel } from "@/hooks/use-org";
import { ROLE_ORDER } from "@/lib/model";
import { cn } from "@/lib/utils";

export function Overview() {
  const t = useTranslations();
  const model = useModel();
  const events = useEvents(8);
  const s = model.state;

  const roleCounts = ROLE_ORDER.map((r) => ({
    role: t(`roles.${r}`),
    count: r === "executor"
      ? new Set(s.tasks.filter((x) => x.owner && x.process).map((x) => `${x.process}|${x.owner}`)).size
      : s.roles.filter((x) => x.role === r).length,
  }));
  const deptData = [...s.departments.map((d) => ({ name: d.name, value: model.membersOf(d.id).length })), { name: t("org.noDepartment"), value: model.membersOf(0).length }]
    .filter((d) => d.value > 0);
  const health = Math.round(((model.coverage.owner + model.coverage.tasks + model.coverage.supervisor + model.coverage.backup) / 4) * 100);
  const excessive = model.workload.filter((w) => w.excessive);
  const noSupervisor = s.processes.filter((p) => !model.hasRole(p.id, "supervisor") && !model.hasRole(p.id, "approver"));
  const duplicate = s.processes.filter((p) => (model.issues.get(p.id) ?? []).some((i) => i.code === "multi_owner"));
  const noOwner = s.processes.filter((p) => !model.hasRole(p.id, "owner"));

  const attention: { icon: typeof AlertTriangle; label: string; count: number; href: string; tone: "danger" | "warn" | "info" }[] = [
    { icon: ShieldAlert, label: t("overview.att.noOwner"), count: noOwner.length + model.unassignedTasks.length, href: "/gaps", tone: "danger" },
    { icon: Gauge, label: t("overview.att.excessive"), count: excessive.length, href: "/workload", tone: "warn" },
    { icon: Copy, label: t("overview.att.duplicate"), count: duplicate.length, href: "/gaps", tone: "warn" },
    { icon: BadgeCheck, label: t("overview.att.pending"), count: s.meta.pending_approvals, href: "/approvals", tone: "info" },
    { icon: CircleDot, label: t("overview.att.noSupervisor"), count: noSupervisor.length, href: "/gaps", tone: "warn" },
  ];

  return (
    <Page>
      <PageHeader
        title={t("overview.title")}
        description={t("overview.description", { company: s.meta.company })}
        actions={<>
          <Button asChild variant="outline"><Link href="/ask">{t("nav.ask")}</Link></Button>
          <Button asChild><Link href="/organization"><Network className="size-4" />{t("overview.openMap")}</Link></Button>
        </>}
      />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard icon={Users} label={t("kpi.employees")} value={s.members.length} hint={t("kpi.teams", { count: s.teams.length })} />
        <StatCard icon={Building2} label={t("kpi.departments")} value={s.departments.length} />
        <StatCard icon={ListChecks} label={t("kpi.responsibilities")} value={s.tasks.length} progress={model.coverage.tasks} />
        <StatCard icon={Workflow} label={t("kpi.processes")} value={s.processes.length} progress={model.coverage.owner} />
        <StatCard icon={ShieldAlert} label={t("kpi.unassigned")} value={model.unassignedTasks.length + noOwner.length} tone={model.unassignedTasks.length + noOwner.length ? "danger" : "success"} />
        <StatCard icon={AlertTriangle} label={t("kpi.conflicts")} value={model.conflicts + duplicate.length} tone={model.conflicts ? "warning" : "success"} />
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-3">
        <ChartCard title={t("overview.health")} description={t("overview.healthHint")}>
          <div className="relative h-56">
            <ResponsiveContainer>
              <RadialBarChart innerRadius="72%" outerRadius="100%" data={[{ value: health }]} startAngle={220} endAngle={-40}>
                <PolarAngleAxis type="number" domain={[0, 100]} tick={false} />
                <RadialBar dataKey="value" cornerRadius={10} fill={health >= 75 ? CHART.success : health >= 50 ? CHART.warning : "var(--destructive)"} background={{ fill: "var(--muted)" }} />
              </RadialBarChart>
            </ResponsiveContainer>
            <div className="absolute inset-0 grid place-items-center">
              <div className="text-center"><div className="font-mono text-4xl font-semibold">{health}%</div><div className="text-xs text-muted-foreground">{t("overview.coverage")}</div></div>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-2 text-xs">
            {([["owner", model.coverage.owner], ["tasks", model.coverage.tasks], ["supervisor", model.coverage.supervisor], ["backup", model.coverage.backup]] as const).map(([k, v]) => (
              <div key={k} className="flex justify-between rounded-md bg-muted/50 px-2.5 py-1.5"><span className="text-muted-foreground">{t(`overview.cov.${k}`)}</span><b className="font-mono">{Math.round(v * 100)}%</b></div>
            ))}
          </div>
        </ChartCard>

        <ChartCard title={t("overview.deptDistribution")} description={t("overview.deptHint")}>
          <div className="h-56">
            <ResponsiveContainer>
              <PieChart>
                <Pie data={deptData} dataKey="value" nameKey="name" innerRadius={55} outerRadius={85} paddingAngle={3} stroke="var(--card)">
                  {deptData.map((_, i) => <Cell key={i} fill={SERIES[i % SERIES.length]} />)}
                </Pie>
                <Tooltip {...tooltipStyle} />
              </PieChart>
            </ResponsiveContainer>
          </div>
          <div className="grid gap-1.5 text-xs">
            {deptData.map((d, i) => (
              <div key={d.name} className="flex items-center gap-2"><span className="size-2 rounded-full" style={{ background: SERIES[i % SERIES.length] }} /><span className="flex-1 truncate">{d.name}</span><b className="font-mono">{d.value}</b></div>
            ))}
          </div>
        </ChartCard>

        <ChartCard title={t("overview.roleDistribution")} description={t("overview.roleHint")}>
          <div className="h-72">
            <ResponsiveContainer>
              <BarChart data={roleCounts} layout="vertical" margin={{ left: 10, right: 16 }}>
                <XAxis type="number" {...axisProps} />
                <YAxis type="category" dataKey="role" width={96} {...axisProps} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="count" radius={[0, 6, 6, 0]} barSize={16}>
                  {roleCounts.map((_, i) => <Cell key={i} fill={i === 0 ? CHART.primary : i === 2 ? CHART.violet : CHART.muted} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </ChartCard>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <Card className="gap-1 p-5">
          <h3 className="mb-2 text-sm font-semibold">{t("overview.attention")}</h3>
          {attention.map((a) => (
            <Link key={a.label} href={a.href} className="-mx-2 flex items-center gap-3 rounded-lg px-2 py-2.5 hover:bg-muted">
              <span className={cn("grid size-8 place-items-center rounded-lg border", a.count === 0 ? "text-success" : a.tone === "danger" ? "text-destructive" : a.tone === "warn" ? "text-warning" : "text-primary")}>
                <a.icon className="size-4" />
              </span>
              <span className="flex-1 text-sm">{a.label}</span>
              <span className={cn("font-mono text-sm", a.count === 0 && "text-muted-foreground")}>{a.count}</span>
            </Link>
          ))}
        </Card>
        <Card className="gap-0 p-5">
          <div className="mb-1 flex items-center"><h3 className="text-sm font-semibold">{t("overview.activity")}</h3>
            <Button asChild variant="ghost" size="sm" className="ml-auto"><Link href="/audit">{t("top.viewAll")}</Link></Button></div>
          <div className="divide-y">
            {(events.data ?? []).map((e) => <ActivityItem key={e.id} event={e} compact />)}
            {events.data?.length === 0 && <p className="py-6 text-center text-sm text-muted-foreground">{t("top.noNotifications")}</p>}
          </div>
        </Card>
      </div>
    </Page>
  );
}
