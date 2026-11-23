"use client";

import { useQuery } from "@tanstack/react-query";
import type { LucideIcon } from "lucide-react";
import Link from "next/link";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { axisProps, CHART, tooltipStyle } from "@/components/charts/chart-kit";
import { Skeleton } from "@/components/ui/skeleton";

import { supportApi, type ExploreRow, type Range } from "./api";
import { Panel } from "./common";
import { dimLabel, ExploreLink, fmtMetric } from "./explore";
import type { SKey, ST } from "./i18n";

const METRICS = "count,bot,staff,unanswered,rate,median_s";
const rangeParams = (r: Range): Record<string, string> =>
  Object.fromEntries(Object.entries(r).filter(([, v]) => v != null && v !== "").map(([k, v]) => [k, String(v)]));

/** Bir o'lchov bo'yicha taqsimot: chapda grafik (bot / xodim / javobsiz / boshqa — ustma-ust), o'ngda to'liq jadval.
 *  Qatorni bosish — aynan o'sha savollar ro'yxati. Hisob konstruktordan (tahlil bilan bir xil). */
export function Breakdown({ by, title, hint, icon, range, t, limit = 15, scope = "analytics" }: {
  by: string; title: string; hint?: string; icon?: LucideIcon; range: Range; t: ST; limit?: number; scope?: string;
}) {
  const params = { dataset: "questions", by, metrics: METRICS, scope, ...rangeParams(range) };
  const q = useQuery({ queryKey: ["support", "explore", params], queryFn: () => supportApi.explore(params) });
  const d = q.data;
  const label = (r: ExploreRow) => dimLabel(t, by, String(r.k0 ?? ""), String(r.l0 ?? ""));
  const rows = (d?.rows ?? []).slice(0, limit);
  const data = rows.map((r) => {
    const n = Number(r.count ?? 0), bot = Number(r.bot ?? 0), staff = Number(r.staff ?? 0), un = Number(r.unanswered ?? 0);
    return { name: label(r), bot, staff, unanswered: un, other: Math.max(0, n - bot - staff - un) };
  });
  const inbox = (r: ExploreRow) => `/support?${new URLSearchParams({ ex: "1", scope, ...rangeParams(range), [`f_${by}`]: String(r.k0 ?? "") }).toString()}`;
  return (
    <Panel title={title} hint={hint} icon={icon} actions={<ExploreLink params={params}>{t("exInBuilder")}</ExploreLink>}>
      {!d ? <Skeleton className="h-64" /> : rows.length === 0 ? <p className="text-sm text-muted-foreground">{t("empty")}</p> : (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div style={{ height: Math.max(200, rows.length * 28 + 50) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} layout="vertical" margin={{ left: 4, right: 12, top: 4, bottom: 4 }}>
                <CartesianGrid horizontal={false} stroke={CHART.grid} strokeDasharray="3 3" />
                <XAxis type="number" {...axisProps} allowDecimals={false} />
                <YAxis type="category" dataKey="name" {...axisProps} width={150} tickFormatter={(v: string) => (v.length > 22 ? v.slice(0, 21) + "…" : v)} />
                <Tooltip {...tooltipStyle} />
                <Legend wrapperStyle={{ fontSize: 12 }} />
                <Bar dataKey="bot" name={t("ex_m_bot")} stackId="a" fill={CHART.success} maxBarSize={20} />
                <Bar dataKey="staff" name={t("ex_m_staff")} stackId="a" fill={CHART.primary} maxBarSize={20} />
                <Bar dataKey="unanswered" name={t("ex_m_unanswered")} stackId="a" fill={CHART.warning} maxBarSize={20} />
                <Bar dataKey="other" name={t("exOther")} stackId="a" fill={CHART.muted} maxBarSize={20} radius={[0, 4, 4, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="text-xs text-muted-foreground">
                <tr className="border-b text-left">
                  <th className="py-1.5 pr-2 font-medium">{t(`ex_d_${by}` as SKey)}</th>
                  {METRICS.split(",").map((m) => <th key={m} className="py-1.5 pl-2 text-right font-medium">{t(`ex_m_${m}` as SKey)}</th>)}
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={String(r.k0)} className="border-b last:border-0 hover:bg-muted/40">
                    <td className="max-w-56 py-1.5 pr-2"><Link href={inbox(r)} className="block truncate hover:text-primary hover:underline">{label(r)}</Link></td>
                    {METRICS.split(",").map((m) => <td key={m} className="py-1.5 pl-2 text-right font-mono text-xs tabular-nums">{fmtMetric(t, m, r[m] as number | null)}</td>)}
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t text-xs font-semibold">
                  <td className="py-1.5 pr-2">{t("exTotal")}</td>
                  {METRICS.split(",").map((m) => <td key={m} className="py-1.5 pl-2 text-right font-mono tabular-nums">{fmtMetric(t, m, d.totals[m])}</td>)}
                </tr>
              </tfoot>
            </table>
            {(d.rows.length > limit) && <p className="mt-1 text-[11px] text-muted-foreground">{t("exTrunc", { n: limit, all: d.rows.length })}</p>}
          </div>
        </div>
      )}
    </Panel>
  );
}
