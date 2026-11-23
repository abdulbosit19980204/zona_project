"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, Inbox, Tags, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Skeleton } from "@/components/ui/skeleton";

import { supportApi, type Explore, type ExploreRow, type Range } from "./api";
import { Initials, Metric, Panel } from "./common";
import { DataTable, type Column } from "./data-table";
import { dimLabel, ExploreLink, fmtMetric } from "./explore";
import type { SKey, ST } from "./i18n";

const METRICS = "count,bot,staff,unanswered,yes,no,open,rate,median_s";
const rangeParams = (r: Range): Record<string, string> =>
  Object.fromEntries(Object.entries(r).filter(([, v]) => v != null && v !== "").map(([k, v]) => [k, String(v)]));

/** Agentlar (savol beruvchilar): kim qancha so'radi, bot / xodim javobi, natija, tezlik; bosib — to'liq tafsilot. */
export function AskersBoard({ range, t }: { range: Range; t: ST }) {
  const params = { dataset: "questions", by: "asker", metrics: METRICS, scope: "analytics", ...rangeParams(range) };
  const q = useQuery({ queryKey: ["support", "explore", params], queryFn: () => supportApi.explore(params) });
  const [open, setOpen] = useState<{ id: string; name: string } | null>(null);
  const d = q.data;
  if (!d) return <Skeleton className="h-96" />;
  const name = (r: ExploreRow) => String(r.l0 ?? "—");
  const columns: Column<ExploreRow>[] = [
    { key: "name", header: t("exAsker"), sort: (r) => name(r).toLowerCase(), cell: (r) => {
      const m = d.asker_meta[String(r.k0)];
      return (
        <button type="button" onClick={() => setOpen({ id: String(r.k0), name: name(r) })} className="flex min-w-52 items-center gap-2.5 text-left hover:underline">
          <Initials name={name(r)} className="size-8" />
          <span className="min-w-0">
            <span className="block font-medium">{name(r)}</span>
            <span className="block max-w-72 truncate text-[11px] text-muted-foreground">
              {m ? [m.role, m.project, m.territory, m.username && "@" + m.username].filter(Boolean).join(" · ") : ""}
            </span>
          </span>
        </button>
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
      <Sheet open={!!open} onOpenChange={(v) => !v && setOpen(null)}>
        <SheetContent className="w-full gap-0 overflow-y-auto p-0 sm:max-w-4xl">
          {open && <AskerDetail id={open.id} name={open.name} range={range} t={t} meta={d.asker_meta[open.id]} />}
        </SheetContent>
      </Sheet>
    </div>
  );
}

function useEx(params: Record<string, string>) {
  return useQuery({ queryKey: ["support", "explore", params], queryFn: () => supportApi.explore(params) }).data;
}

function AskerDetail({ id, name, range, t, meta }: { id: string; name: string; range: Range; t: ST; meta?: Explore["asker_meta"][string] }) {
  const base = { dataset: "questions", scope: "all", f_asker: id, ...rangeParams(range) };
  const days = useEx({ ...base, by: "day", metrics: "count,bot,unanswered" });
  const topics = useEx({ ...base, by: "topic", metrics: "count,bot,unanswered,yes,no" });
  const staff = useEx({ ...base, by: "staff", metrics: "count,median_s" });
  const res = useEx({ ...base, by: "resolution", metrics: "count" });
  const inbox = `/support?${new URLSearchParams({ ex: "1", scope: "all", f_asker: id, ...rangeParams(range) }).toString()}`;
  const tot = topics?.totals ?? {};
  return (
    <>
      <SheetHeader className="border-b">
        <SheetTitle className="flex items-center gap-2.5 pr-6"><Initials name={name} className="size-8" />{name}</SheetTitle>
        <p className="text-xs text-muted-foreground">{meta ? [meta.role, meta.project, meta.territory, meta.username && "@" + meta.username].filter(Boolean).join(" · ") : ""}</p>
        <div className="flex gap-4 pt-1 text-xs">
          <Link href={inbox} className="inline-flex items-center gap-1 text-primary hover:underline"><Inbox className="size-3.5" />{t("exQuestionsList")}</Link>
          <ExploreLink params={{ ...base, by: "month,topic", metrics: "count,bot,unanswered,median_s" }}>{t("exInBuilder")}</ExploreLink>
        </div>
      </SheetHeader>
      {!topics ? <div className="p-4"><Skeleton className="h-80" /></div> : (
        <div className="grid gap-4 p-4">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric label={t("ex_m_count")} value={fmtMetric(t, "count", tot.count)} />
            <Metric label={t("ex_m_bot")} value={fmtMetric(t, "bot", tot.bot)} />
            <Metric label={t("ex_m_unanswered")} value={fmtMetric(t, "unanswered", tot.unanswered)} />
            <Metric label={t("ex_m_yes")} value={`${fmtMetric(t, "yes", tot.yes)} / ${fmtMetric(t, "no", tot.no)}`} hint={t("exYesNo")} />
          </div>
          {days && days.rows.length > 0 && (
            <Panel title={t("exByDay")} icon={CalendarDays}>
              <Columns rows={days.rows} t={t} />
            </Panel>
          )}
          <div className="grid gap-4 lg:grid-cols-2">
            <Panel title={t("ex_d_topic")} icon={Tags}><Bars rows={topics.rows} dim="topic" t={t} /></Panel>
            <div className="grid content-start gap-4">
              {res && <Panel title={t("ex_d_resolution")}><Bars rows={res.rows} dim="resolution" t={t} /></Panel>}
              {staff && <Panel title={t("exWhoAnswered")} icon={UserRound}><Bars rows={staff.rows} dim="staff" t={t} extra="median_s" /></Panel>}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/** Kunlar: ustunlar (bot — yashil qism, javobsiz — sariq), hover'da qiymat. */
function Columns({ rows, t }: { rows: ExploreRow[]; t: ST }) {
  const max = Math.max(1, ...rows.map((r) => Number(r.count ?? 0)));
  return (
    <div className="flex h-36 items-end gap-[2px] overflow-x-auto pb-5">
      {rows.map((r) => {
        const n = Number(r.count ?? 0);
        const bot = Number(r.bot ?? 0);
        return (
          <div key={String(r.k0)} className="group relative flex h-full min-w-[10px] flex-1 flex-col justify-end"
            title={`${r.k0}: ${n} · ${t("ex_m_bot")} ${bot} · ${t("ex_m_unanswered")} ${r.unanswered ?? 0}`}>
            <div className="flex w-full flex-col justify-end overflow-hidden rounded-t-[3px] bg-primary/70" style={{ height: `${(100 * n) / max}%` }}>
              <div className="w-full bg-success/80" style={{ height: `${n ? (100 * bot) / n : 0}%` }} />
            </div>
            <span className="absolute -bottom-4 left-1/2 hidden -translate-x-1/2 whitespace-nowrap text-[10px] text-muted-foreground group-hover:block">{String(r.k0).slice(5)}</span>
          </div>
        );
      })}
    </div>
  );
}

function Bars({ rows, dim, t, extra }: { rows: ExploreRow[]; dim: string; t: ST; extra?: string }) {
  const max = Math.max(1, ...rows.map((r) => Number(r.count ?? 0)));
  if (!rows.length) return <p className="text-sm text-muted-foreground">{t("empty")}</p>;
  return (
    <div className="grid gap-1.5">
      {rows.slice(0, 12).map((r) => (
        <div key={String(r.k0)} className="grid grid-cols-[1fr_auto] items-center gap-2 text-sm">
          <div className="min-w-0">
            <div className="truncate">{dimLabel(t, dim, String(r.k0 ?? ""), String(r.l0 ?? ""))}</div>
            <div className="mt-0.5 h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${(100 * Number(r.count ?? 0)) / max}%` }} /></div>
          </div>
          <span className="font-mono text-xs tabular-nums">{r.count}{extra && r[extra] != null && <span className="text-muted-foreground"> · {fmtMetric(t, extra, r[extra] as number)}</span>}</span>
        </div>
      ))}
    </div>
  );
}
