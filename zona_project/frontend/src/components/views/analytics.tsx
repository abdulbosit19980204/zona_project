"use client";

import { useTranslations } from "next-intl";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { axisProps, CHART, ChartCard, SERIES, tooltipStyle } from "@/components/charts/chart-kit";
import { Page, PageHeader, StatCard } from "@/components/common/page";
import { useModel } from "@/hooks/use-org";
import { PROCESS_ROLES } from "@/lib/model";

/** Mas'uliyat tahlili: rollar qamrovi, bo'limlar bo'yicha taqsimot, tizimlar bo'yicha muammolar, egalik jamlanishi. */
export function Analytics() {
  const t = useTranslations();
  const model = useModel();
  const c = model.coverage;
  const pct = (v: number) => `${Math.round(v * 100)}%`;

  const deptIds = [...model.state.departments.map((d) => d.id), 0].filter((d) => model.membersOf(d).length);
  const byDept = deptIds.map((d) => {
    const row: Record<string, string | number> = { name: model.dept.get(d)?.name ?? t("org.noDepartment") };
    for (const r of PROCESS_ROLES) row[r] = 0;
    row.executor = 0;
    for (const m of model.membersOf(d)) {
      for (const l of model.linksOfMember.get(m.id) ?? []) for (const r of l.roles) row[r] = Number(row[r]) + 1;
    }
    return row;
  });

  const bySystem = model.state.systems.map((s) => {
    const ps = model.state.processes.filter((p) => p.system === s.id);
    return {
      name: s.name,
      ok: ps.filter((p) => !model.level(p.id)).length,
      warn: ps.filter((p) => model.level(p.id) === "warn").length,
      danger: ps.filter((p) => model.level(p.id) === "danger").length,
    };
  }).filter((r) => r.ok + r.warn + r.danger);

  const concentration = model.workload
    .map((w) => ({ name: w.member.name, owned: w.owned, approvals: w.approvals }))
    .filter((r) => r.owned + r.approvals)
    .sort((a, b) => b.owned - a.owned)
    .slice(0, 10);

  const totalOwned = model.state.processes.length || 1;
  const topShare = concentration.slice(0, 2).reduce((s, r) => s + r.owned, 0) / totalOwned;

  return (
    <Page>
      <PageHeader title={t("nav.analytics")} description={t("analytics.description")} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label={t("overview.cov.owner")} value={pct(c.owner)} progress={c.owner} />
        <StatCard label={t("overview.cov.supervisor")} value={pct(c.supervisor)} progress={c.supervisor} />
        <StatCard label={t("overview.cov.approver")} value={pct(c.approver)} progress={c.approver} />
        <StatCard label={t("overview.cov.backup")} value={pct(c.backup)} progress={c.backup} tone={c.backup < 0.5 ? "warning" : "default"} />
        <StatCard label={t("overview.cov.tasks")} value={pct(c.tasks)} progress={c.tasks} />
      </div>
      <div className="mt-4 grid gap-4 xl:grid-cols-2">
        <ChartCard title={t("analytics.rolesByDept")} description={t("analytics.rolesByDeptHint")}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={byDept} margin={{ left: -16 }}>
              <CartesianGrid vertical={false} stroke={CHART.grid} />
              <XAxis dataKey="name" {...axisProps} />
              <YAxis {...axisProps} allowDecimals={false} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {(["owner", "executor", ...PROCESS_ROLES.filter((r) => r !== "owner")] as const).map((r, i) => (
                <Bar key={r} dataKey={r} name={t(`roles.${r}`)} stackId="a" fill={SERIES[i % SERIES.length]} maxBarSize={48} />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title={t("analytics.bySystem")} description={t("analytics.bySystemHint")}>
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={bySystem} layout="vertical" margin={{ left: 8 }}>
              <CartesianGrid horizontal={false} stroke={CHART.grid} />
              <XAxis type="number" {...axisProps} allowDecimals={false} />
              <YAxis type="category" dataKey="name" {...axisProps} width={120} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="ok" name={t("analytics.ok")} stackId="s" fill={CHART.success} maxBarSize={22} />
              <Bar dataKey="warn" name={t("analytics.warn")} stackId="s" fill={CHART.warning} maxBarSize={22} />
              <Bar dataKey="danger" name={t("analytics.danger")} stackId="s" fill="var(--destructive)" maxBarSize={22} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard
          className="xl:col-span-2"
          title={t("analytics.concentration")}
          description={t("analytics.concentrationHint", { share: pct(topShare) })}
        >
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={concentration} margin={{ left: -16 }}>
              <CartesianGrid vertical={false} stroke={CHART.grid} />
              <XAxis dataKey="name" {...axisProps} />
              <YAxis {...axisProps} allowDecimals={false} />
              <Tooltip {...tooltipStyle} />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="owned" name={t("roles.owner")} fill={CHART.primary} radius={[4, 4, 0, 0]} maxBarSize={40} />
              <Bar dataKey="approvals" name={t("roles.approver")} fill={CHART.violet} radius={[4, 4, 0, 0]} maxBarSize={40} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
      </div>
    </Page>
  );
}
