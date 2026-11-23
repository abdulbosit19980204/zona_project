"use client";

import { useQuery } from "@tanstack/react-query";
import { Inbox, UserRound, Users } from "lucide-react";
import Link from "next/link";

import { Skeleton } from "@/components/ui/skeleton";

import { supportApi, type ExploreRow, type Range } from "./api";
import { Initials, Metric, Panel } from "./common";
import { DataTable, type Column } from "./data-table";
import { ExploreLink, fmtMetric } from "./explore";
import type { SKey, ST } from "./i18n";

const METRICS = "count,bot,staff,unanswered,yes,no,open,rate,median_s";
const rangeParams = (r: Range): Record<string, string> =>
  Object.fromEntries(Object.entries(r).filter(([, v]) => v != null && v !== "").map(([k, v]) => [k, String(v)]));

/** Agentlar (savol beruvchilar): kim qancha so'radi, bot / xodim javobi, natija, tezlik; bosib — to'liq tafsilot. */
export function AskersBoard({ range, t }: { range: Range; t: ST }) {
  const params = { dataset: "questions", by: "asker", metrics: METRICS, scope: "analytics", ...rangeParams(range) };
  const q = useQuery({ queryKey: ["support", "explore", params], queryFn: () => supportApi.explore(params) });
  const d = q.data;
  if (!d) return <Skeleton className="h-96" />;
  const name = (r: ExploreRow) => String(r.l0 ?? "—");
  const columns: Column<ExploreRow>[] = [
    { key: "name", header: t("exAsker"), sort: (r) => name(r).toLowerCase(), cell: (r) => {
      const m = d.asker_meta[String(r.k0)];
      return (
        <Link href={`/support/askers/${r.k0}`} className="flex min-w-52 items-center gap-2.5 text-left hover:underline">
          <Initials name={name(r)} className="size-8" />
          <span className="min-w-0">
            <span className="block font-medium">{name(r)}</span>
            <span className="block max-w-72 truncate text-[11px] text-muted-foreground">
              {m ? [m.role, m.project, m.territory, m.username && "@" + m.username].filter(Boolean).join(" · ") : ""}
            </span>
          </span>
        </Link>
      );
    } },
    ...METRICS.split(",").map((m) => ({
      key: m, header: t(`ex_m_${m}` as SKey), align: "right" as const, sort: (r: ExploreRow) => Number(r[m] ?? -1),
      cell: (r: ExploreRow) => <span className="font-mono text-xs">{fmtMetric(t, m, r[m] as number | null)}</span>,
    })),
  ];
  return (
    <div className="grid gap-3">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label={t("exAskers")} value={d.rows.length} icon={Users} tone="primary" />
        <Metric label={t("ex_m_count")} value={fmtMetric(t, "count", d.totals.count)} icon={Inbox} />
        <Metric label={t("ex_m_bot")} value={fmtMetric(t, "bot", d.totals.bot)} tone="success" />
        <Metric label={t("ex_m_open")} value={fmtMetric(t, "open", d.totals.open)} tone="warning" />
        <Metric label={t("ex_m_median_s")} value={fmtMetric(t, "median_s", d.totals.median_s)} />
      </div>
      <Panel title={t("anAskers")} hint={t("exAskersHint")} icon={UserRound}
        actions={<ExploreLink params={{ ...params, by: "asker,resolution" }}>{t("exInBuilder")}</ExploreLink>}>
        <DataTable rows={d.rows} columns={columns} rowKey={(r) => String(r.k0)} t={t} initialSort={{ key: "count", dir: "desc" }} pageSize={100}
          search={(r) => { const m = d.asker_meta[String(r.k0)]; return [name(r), m?.username, m?.role, m?.project, m?.territory].filter(Boolean).join(" "); }} />
      </Panel>

    </div>
  );
}
