"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Download, Filter, Inbox, Plus, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { axisProps, CHART, SERIES, tooltipStyle } from "@/components/charts/chart-kit";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";

import { supportApi, type Explore, type ExploreRow } from "./api";
import { fmtDur, Panel, Segmented } from "./common";
import { DataTable, type Column } from "./data-table";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";

type Dataset = "questions" | "staff" | "activity";
const PRESETS = ["1", "7", "30", "90", "365", "3650"];
const DEFAULTS: Record<Dataset, { by: string; metrics: string }> = {
  questions: { by: "day", metrics: "count,bot,staff,unanswered,rate,median_s" },
  staff: { by: "staff", metrics: "count,answers,clarifications,handoffs,median_s" },
  activity: { by: "person", metrics: "messages,days" },
};

/** Metrika qiymatini ko'rsatish: soniya — davomiylik, ulush — %. */
export function fmtMetric(t: ST, m: string, v: number | null | undefined) {
  if (v == null) return "—";
  if (m.endsWith("_s")) return fmtDur(t, v);
  if (m === "rate" || m === "bot_share" || m === "within_15") return `${v}%`;
  return v.toLocaleString();
}

/** O'lchov qiymati yorlig'i: holat va natija kalitlari tarjima qilinadi, qolgani — serverdagi nom. */
export function dimLabel(t: ST, dim: string, key: string, label: string) {
  if (dim === "resolution") return t((key === "noma'lum" ? "r_" : `r_${key}`) as SKey);
  if (dim === "status") return t(`m_${key}` as SKey);
  if (dim === "category" && key && key !== "—") return t(`cat_${key}` as SKey);
  if (dim === "app" && key && key !== "—") return t(`sys_${key}` as SKey);
  if (dim === "origin" && key && key !== "—") return t(`org_${key}` as SKey);
  return label || "—";
}

export function SupportExplore() {
  return <Suspense><ExploreInner /></Suspense>;
}

/** Konstruktor: holat URL'da (havola bilan ulashiladi) — ma'lumot turi, davr, guruhlash, ko'rsatkichlar, filtrlar. */
function ExploreInner() {
  const t = useSt();
  const router = useRouter();
  const pathname = usePathname();
  const sp = useSearchParams();
  const dataset = (["questions", "staff", "activity"].includes(sp.get("dataset") ?? "") ? sp.get("dataset") : "questions") as Dataset;
  const params = useMemo(() => {
    const p: Record<string, string> = { dataset, by: sp.get("by") ?? DEFAULTS[dataset].by, metrics: sp.get("metrics") ?? DEFAULTS[dataset].metrics,
      scope: sp.get("scope") ?? "analytics" };
    if (sp.get("from") || sp.get("to")) { p.from = sp.get("from") || sp.get("to")!; p.to = sp.get("to") || sp.get("from")!; }
    else p.days = sp.get("days") ?? "30";
    sp.forEach((v, k) => { if (k.startsWith("f_") && v) p[k] = v; });
    return p;
  }, [sp, dataset]);
  const set = (patch: Record<string, string | null>) => {
    const next = new URLSearchParams(sp.toString());
    Object.entries(patch).forEach(([k, v]) => (v ? next.set(k, v) : next.delete(k)));
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  };
  const q = useQuery({ queryKey: ["support", "explore", params], queryFn: () => supportApi.explore(params), placeholderData: keepPreviousData });
  const d = q.data;
  const by = params.by ? params.by.split(",").filter(Boolean) : [];
  const metrics = params.metrics.split(",").filter(Boolean);
  const filters = Object.entries(params).filter(([k]) => k.startsWith("f_")).map(([k, v]) => [k.slice(2), v.split(",")] as const);
  const custom = !!(params.from || params.to);

  return (
    <SupportShell title={t("exTitle")} description={t("exDesc")}>
      <div className="grid gap-3">
        <Panel bodyClassName="grid gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <Segmented size="sm" value={dataset} onChange={(v) => set({ dataset: v, by: null, metrics: null, ...Object.fromEntries(filters.map(([k]) => [`f_${k}`, null])) })}
              options={(["questions", "staff", "activity"] as Dataset[]).map((x) => ({ value: x, label: t(`ex_ds_${x}` as SKey) }))} />
            <Segmented size="sm" value={custom ? "custom" : params.days} onChange={(v) => set(v === "custom" ? { days: null, from: d?.from ?? "", to: d?.to ?? "" } : { days: v, from: null, to: null })}
              options={[...PRESETS.map((x) => ({ value: x, label: t(`ex_p_${x}` as SKey) })), { value: "custom", label: t("daysCustom") }]} />
            {custom && (
              <span className="flex items-center gap-1">
                <Input type="date" className="h-8 w-36 text-xs" value={params.from ?? ""} onChange={(e) => set({ from: e.target.value })} aria-label={t("dateFrom")} />
                <span className="text-xs text-muted-foreground">—</span>
                <Input type="date" className="h-8 w-36 text-xs" value={params.to ?? ""} onChange={(e) => set({ to: e.target.value })} aria-label={t("dateTo")} />
              </span>
            )}
            {dataset !== "activity" && (
              <Segmented size="sm" value={params.scope} onChange={(v) => set({ scope: v })}
                options={["analytics", "live", "all"].map((x) => ({ value: x, label: t(`ex_sc_${x}` as SKey) }))} />
            )}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <Pick label={t("exBy1")} value={by[0] ?? ""} dims={d?.dims ?? []} t={t} onChange={(v) => set({ by: [v, by[1]].filter(Boolean).join(",") || "" })} empty={t("exNone")} />
            <Pick label={t("exBy2")} value={by[1] ?? ""} dims={(d?.dims ?? []).filter((x) => x !== by[0])} t={t} disabled={!by[0]}
              onChange={(v) => set({ by: [by[0], v].filter(Boolean).join(",") })} empty={t("exNone")} />
            <AddFilter d={d} t={t} used={filters.map(([k]) => k)} onAdd={(dim, keys) => set({ [`f_${dim}`]: keys.join(",") })} />
          </div>
          <div className="flex flex-wrap items-center gap-1.5">
            <span className="mr-1 text-xs text-muted-foreground">{t("exMetrics")}:</span>
            {(d?.all_metrics ?? []).map((m) => {
              const on = metrics.includes(m);
              return (
                <button key={m} type="button" onClick={() => set({ metrics: (on ? metrics.filter((x) => x !== m) : [...metrics, m]).join(",") || m })}
                  className={`rounded-full border px-2.5 py-0.5 text-xs transition-colors ${on ? "border-primary/50 bg-primary/10 font-medium text-primary" : "text-muted-foreground hover:bg-muted"}`}>
                  {t(`ex_m_${m}` as SKey)}
                </button>
              );
            })}
          </div>
          {filters.length > 0 && (
            <div className="flex flex-wrap items-center gap-1.5">
              <Filter className="size-3.5 text-muted-foreground" />
              {filters.map(([dim, keys]) => (
                <Badge key={dim} variant="outline" className="gap-1 font-normal">
                  {t(`ex_d_${dim}` as SKey)}: {keys.map((k) => dimLabel(t, dim, k, d?.options[dim]?.find((o) => o.key === k)?.label ?? k)).join(", ")}
                  <button type="button" onClick={() => set({ [`f_${dim}`]: null })} aria-label={t("drillClear")}><X className="size-3" /></button>
                </Badge>
              ))}
            </div>
          )}
        </Panel>
        {!d ? <Skeleton className="h-96" /> : <Result d={d} t={t} params={params} loading={q.isFetching} />}
      </div>
    </SupportShell>
  );
}

function Pick({ label, value, dims, onChange, t, empty, disabled }: {
  label: string; value: string; dims: string[]; onChange: (v: string) => void; t: ST; empty: string; disabled?: boolean;
}) {
  return (
    <label className="flex items-center gap-2">
      <span className="text-xs text-muted-foreground">{label}</span>
      <select className="h-8 rounded-md border bg-background px-2 text-sm" value={value} disabled={disabled} onChange={(e) => onChange(e.target.value)}>
        <option value="">{empty}</option>
        {dims.map((x) => <option key={x} value={x}>{t(`ex_d_${x}` as SKey)}</option>)}
      </select>
    </label>
  );
}

/** Filtr qo'shish: o'lchov -> qiymatlar (soni bilan, qidiruv bilan). */
function AddFilter({ d, t, used, onAdd }: { d?: Explore; t: ST; used: string[]; onAdd: (dim: string, keys: string[]) => void }) {
  const [dim, setDim] = useState("");
  const [sel, setSel] = useState<string[]>([]);
  const [q, setQ] = useState("");
  const opts = (d?.options[dim] ?? []).filter((o) => !q || dimLabel(t, dim, o.key, o.label).toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="relative">
      <select className="h-8 rounded-md border bg-background px-2 text-sm" value={dim} onChange={(e) => { setDim(e.target.value); setSel([]); setQ(""); }}>
        <option value="">+ {t("exAddFilter")}</option>
        {(d?.dims ?? []).filter((x) => !used.includes(x)).map((x) => <option key={x} value={x}>{t(`ex_d_${x}` as SKey)}</option>)}
      </select>
      {dim && (
        <div className="absolute left-0 top-9 z-20 grid w-80 gap-2 rounded-lg border bg-popover p-2 shadow-lg">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-8" autoFocus />
          <div className="grid max-h-64 gap-0.5 overflow-y-auto">
            {opts.map((o) => (
              <label key={o.key} className="flex cursor-pointer items-center gap-2 rounded px-1.5 py-1 text-sm hover:bg-muted">
                <input type="checkbox" checked={sel.includes(o.key)} onChange={() => setSel(sel.includes(o.key) ? sel.filter((x) => x !== o.key) : [...sel, o.key])} />
                <span className="min-w-0 flex-1 truncate">{dimLabel(t, dim, o.key, o.label)}</span>
                <span className="text-xs tabular-nums text-muted-foreground">{o.n}</span>
              </label>
            ))}
            {opts.length === 0 && <p className="p-2 text-xs text-muted-foreground">{t("empty")}</p>}
          </div>
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="ghost" onClick={() => setDim("")}>{t("cancel")}</Button>
            <Button size="sm" disabled={!sel.length} onClick={() => { onAdd(dim, sel); setDim(""); }}><Plus className="size-4" />{t("exApply")}</Button>
          </div>
        </div>
      )}
    </div>
  );
}

const keyOf = (r: ExploreRow) => `${r.k0 ?? ""}|${r.k1 ?? ""}`;

function Result({ d, t, params, loading }: { d: Explore; t: ST; params: Record<string, string>; loading: boolean }) {
  const [chartMetric, setChartMetric] = useState("");
  const metric = d.metrics.includes(chartMetric) ? chartMetric : d.metrics[0];
  const drill = (r?: ExploreRow) => {
    if (d.dataset !== "questions") return null;
    const p = new URLSearchParams({ ex: "1", scope: d.scope });
    Object.entries(params).forEach(([k, v]) => { if (k.startsWith("f_") || k === "days" || k === "from" || k === "to") p.set(k, v); });
    if (r) d.by.forEach((dim, i) => { const k = r[`k${i}` as "k0" | "k1"]; if (k != null) p.set(`f_${dim}`, k); });
    return `/support?${p.toString()}`;
  };
  const csv = () => {
    const head = [...d.by.map((x) => t(`ex_d_${x}` as SKey)), ...d.metrics.map((m) => t(`ex_m_${m}` as SKey))];
    const lines = d.rows.map((r) => [...d.by.map((dim, i) => dimLabel(t, dim, String(r[`k${i}` as "k0"] ?? ""), String(r[`l${i}` as "l0"] ?? ""))),
      ...d.metrics.map((m) => r[m] ?? "")]);
    const body = [head, ...lines].map((row) => row.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(",")).join("\n");
    const a = document.createElement("a");
    a.href = URL.createObjectURL(new Blob(["﻿" + body], { type: "text/csv;charset=utf-8" }));
    a.download = `support-${d.dataset}-${d.from}-${d.to}.csv`;
    a.click();
    URL.revokeObjectURL(a.href);
  };
  const columns: Column<ExploreRow>[] = [
    ...d.by.map((dim, i) => ({
      key: `k${i}`, header: t(`ex_d_${dim}` as SKey), sort: (r: ExploreRow) => String(r[`k${i}` as "k0"] ?? ""),
      cell: (r: ExploreRow) => {
        const meta = dim === "asker" ? d.asker_meta[String(r[`k${i}` as "k0"])] : undefined;
        return (
          <span className="min-w-32">
            <span className="block font-medium">{dimLabel(t, dim, String(r[`k${i}` as "k0"] ?? ""), String(r[`l${i}` as "l0"] ?? ""))}</span>
            {meta && <span className="block text-[11px] text-muted-foreground">{[meta.role, meta.project, meta.territory, meta.username && "@" + meta.username].filter(Boolean).join(" · ")}</span>}
          </span>
        );
      },
    })),
    ...d.metrics.map((m) => ({
      key: m, header: t(`ex_m_${m}` as SKey), align: "right" as const, sort: (r: ExploreRow) => Number(r[m] ?? -1),
      cell: (r: ExploreRow) => <span className="font-mono text-xs">{fmtMetric(t, m, r[m] as number | null)}</span>,
    })),
    ...(d.dataset === "questions" ? [{
      key: "go", header: "", cell: (r: ExploreRow) => (
        <Link href={drill(r)!} className="inline-flex items-center gap-1 text-xs text-primary hover:underline" title={t("anDrill")}>
          <Inbox className="size-3.5" />{t("exOpen")}</Link>
      ),
    }] : []),
  ];
  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-stretch gap-2">
        {d.metrics.map((m) => (
          <button key={m} type="button" onClick={() => setChartMetric(m)}
            className={`min-w-28 rounded-xl border bg-card px-3 py-2 text-left shadow-xs transition-colors ${m === metric ? "border-primary/50 ring-1 ring-primary/30" : "hover:bg-muted/50"}`}>
            <div className="text-[11px] text-muted-foreground">{t(`ex_m_${m}` as SKey)}</div>
            <div className="text-lg font-semibold tabular-nums">{fmtMetric(t, m, d.totals[m])}</div>
          </button>
        ))}
        <div className="ml-auto flex items-center gap-2 self-center">
          {loading && <span className="text-xs text-muted-foreground">…</span>}
          {d.dataset === "questions" && <Button size="sm" variant="outline" asChild><Link href={drill()!}><Inbox className="size-4" />{t("exOpenAll")}</Link></Button>}
          <Button size="sm" variant="outline" onClick={csv} disabled={!d.rows.length}><Download className="size-4" />CSV</Button>
        </div>
      </div>
      {d.by.length > 0 && d.rows.length > 0 && <Chart d={d} t={t} metric={metric} />}
      {d.by.length > 0 && (
        <Panel title={t("exTable")} hint={d.total_rows > d.rows.length ? t("exTrunc", { n: d.rows.length, all: d.total_rows }) : undefined}>
          <DataTable rows={d.rows} columns={columns} rowKey={keyOf} t={t} pageSize={100}
            search={(r) => d.by.map((dim, i) => dimLabel(t, dim, String(r[`k${i}` as "k0"] ?? ""), String(r[`l${i}` as "l0"] ?? ""))).join(" ")} />
        </Panel>
      )}
    </div>
  );
}

/** Grafik: bitta guruhlash — bitta rangli ustunlar; ikkita — ikkinchisi bo'yicha ustma-ust (eng ko'p 5 ta + "Boshqa"). */
function Chart({ d, t, metric }: { d: Explore; t: ST; metric: string }) {
  const additive = !metric.endsWith("_s") && !["rate", "bot_share", "within_15", "askers", "people", "days"].includes(metric);
  const two = d.by.length === 2 && additive;
  const label = (i: number, r: ExploreRow) => dimLabel(t, d.by[i], String(r[`k${i}` as "k0"] ?? ""), String(r[`l${i}` as "l0"] ?? ""));
  const { data, series } = useMemo(() => {
    if (!two) {
      return { data: d.rows.slice(0, 60).map((r) => ({ name: label(0, r), v: Number(r[metric] ?? 0) })), series: [] as string[] };
    }
    const tot = new Map<string, number>();
    d.rows.forEach((r) => tot.set(label(1, r), (tot.get(label(1, r)) ?? 0) + Number(r[metric] ?? 0)));
    const top = [...tot.entries()].sort((a, b) => b[1] - a[1]).slice(0, 5).map(([k]) => k);
    const other = t("exOther");
    const byX = new Map<string, Record<string, number | string>>();
    d.rows.forEach((r) => {
      const x = label(0, r);
      const s = top.includes(label(1, r)) ? label(1, r) : other;
      const row = byX.get(x) ?? { name: x };
      row[s] = Number(row[s] ?? 0) + Number(r[metric] ?? 0);
      byX.set(x, row);
    });
    const has = [...byX.values()].some((r) => r[other] != null);
    return { data: [...byX.values()].slice(0, 40), series: has ? [...top, other] : top };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [d, metric, two]);
  const horizontal = !["day", "week", "month", "hour", "weekday"].includes(d.by[0]);
  const fmt = (v: number) => fmtMetric(t, metric, v);
  const height = horizontal ? Math.max(220, Math.min(data.length, 30) * 26 + 40) : 300;
  return (
    <Panel title={`${t(`ex_m_${metric}` as SKey)} · ${d.by.map((x) => t(`ex_d_${x}` as SKey)).join(" × ")}`}>
      <div style={{ height }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={horizontal ? data.slice(0, 30) : data} layout={horizontal ? "vertical" : "horizontal"} margin={{ left: 8, right: 16, top: 8, bottom: 4 }}>
            <CartesianGrid stroke={CHART.grid} strokeDasharray="3 3" vertical={horizontal} horizontal={!horizontal} />
            {horizontal ? (
              <>
                <XAxis type="number" {...axisProps} tickFormatter={fmt} />
                <YAxis type="category" dataKey="name" {...axisProps} width={170} tickFormatter={(v: string) => (v.length > 26 ? v.slice(0, 25) + "…" : v)} />
              </>
            ) : (
              <>
                <XAxis dataKey="name" {...axisProps} minTickGap={12} />
                <YAxis {...axisProps} tickFormatter={fmt} width={56} />
              </>
            )}
            <Tooltip {...tooltipStyle} formatter={(v) => fmt(Number(v))} />
            {two ? series.map((s, i) => (
              <Bar key={s} dataKey={s} stackId="a" fill={i < 5 ? SERIES[i] : CHART.muted} stroke="var(--card)" strokeWidth={1}
                radius={i === series.length - 1 ? (horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]) : 0} maxBarSize={28} />
            )) : <Bar dataKey="v" name={t(`ex_m_${metric}` as SKey)} fill={CHART.primary} radius={horizontal ? [0, 4, 4, 0] : [4, 4, 0, 0]} maxBarSize={28} />}
            {two && <Legend wrapperStyle={{ fontSize: 12 }} />}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </Panel>
  );
}

export function ExploreLink({ params, children }: { params: Record<string, string>; children: ReactNode }) {
  return <Link href={`/support/explore?${new URLSearchParams(params).toString()}`} className="text-xs text-primary hover:underline">{children}</Link>;
}
