"use client";

import { useQuery } from "@tanstack/react-query";
import { Cpu, Gauge, Image as ImageIcon, Timer, Turtle, Zap } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import { supportApi } from "./api";
import { fmtDate, Metric, Panel, stageLabel } from "./common";
import type { SKey, ST } from "./i18n";

const sec = (v: number | null | undefined) => (v == null ? "—" : `${v} s`);
const PART_KEYS = ["recv", "wait", "queue", "media", "ocr", "decide", "send", "work"] as const;

/** Bot tezligi: savol kelgandan javob yuborilguncha. Qayerda vaqt ketyapti — navbat, OCR, AI yoki yuborish. */
export function Speed({ days, t }: { days: number; t: ST }) {
  const q = useQuery({ queryKey: ["support", "speed", days], queryFn: () => supportApi.speed(Math.min(days, 90)), refetchInterval: 60_000 });
  const d = q.data;
  if (!d) return <Skeleton className="h-96" />;
  const maxB = Math.max(1, ...d.buckets.map((b) => b.n));
  const maxH = Math.max(1, ...d.by_hour.map((h) => h.p90 ?? 0));
  const queueP90 = d.parts.queue?.p90 ?? 0;
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metric label={t("spP50")} value={sec(d.p50)} hint={t("spP50Hint")} icon={Zap} tone="success" />
        <Metric label={t("spP90")} value={sec(d.p90)} hint={t("spP90Hint")} icon={Gauge} tone={(d.p90 ?? 0) > 15 ? "warning" : undefined} />
        <Metric label={t("spWithin5")} value={d.within_5 == null ? "—" : `${d.within_5}%`} icon={Timer} />
        <Metric label={t("spAnswered")} value={d.answered} hint={t("spMax", { n: d.max ?? "—" })} icon={Turtle} />
        <Metric label={t("spWorkers")} value={d.workers} hint={t("spCpu", { n: d.cpu ?? "—" })} icon={Cpu}
          tone={queueP90 > 2 ? "warning" : "primary"} />
      </div>
      {queueP90 > 2 && <p className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{t("spQueueWarn", { n: queueP90 })}</p>}

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("spDist")} hint={t("spDistHint")} icon={Timer}>
          <div className="flex h-36 items-end gap-2 border-b">
            {d.buckets.map((b) => (
              <div key={b.label} className="group flex h-full flex-1 flex-col items-center justify-end gap-1" title={`${b.label}: ${b.n}`}>
                <span className="font-mono text-[11px] tabular-nums">{b.n}</span>
                <div className="w-full max-w-12 rounded-t-[4px] bg-primary group-hover:opacity-80" style={{ height: `${(100 * b.n) / maxB}%`, minHeight: b.n ? 2 : 0 }} />
              </div>
            ))}
          </div>
          <div className="mt-1 flex gap-2">{d.buckets.map((b) => <span key={b.label} className="flex-1 text-center text-[11px] text-muted-foreground">{b.label}</span>)}</div>
        </Panel>
        <Panel title={t("spHour")} hint={t("spHourHint")} icon={Gauge}>
          <div className="flex h-36 items-end gap-[2px] border-b">
            {d.by_hour.map((h) => (
              <div key={h.hour} className="group flex h-full flex-1 flex-col justify-end" title={`${h.hour}:00 — p90 ${sec(h.p90)} · ${t("wlQ", { n: h.n })}`}>
                <div className="rounded-t-[3px] bg-primary group-hover:opacity-80" style={{ height: `${(100 * (h.p90 ?? 0)) / maxH}%`, minHeight: h.n ? 2 : 0, opacity: h.n ? 1 : 0.2 }} />
              </div>
            ))}
          </div>
          <div className="mt-1 flex justify-between text-[10px] text-muted-foreground"><span>0</span><span>6</span><span>12</span><span>18</span><span>23</span></div>
        </Panel>
      </div>

      <Panel title={t("spParts")} hint={t("spPartsHint")} icon={Cpu} bodyClassName="p-0">
        <Table>
          <TableHeader><TableRow className="bg-muted/40">
            <TableHead className="pl-4">{t("spStep")}</TableHead><TableHead className="text-right">{t("spAvg")}</TableHead><TableHead className="pr-4 text-right">p90</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {PART_KEYS.filter((k) => d.parts[k]).map((k) => (
              <TableRow key={k}>
                <TableCell className="pl-4"><div className="font-medium">{t(`sp_${k}` as SKey)}</div><div className="text-xs text-muted-foreground">{t(`sp_${k}_h` as SKey)}</div></TableCell>
                <TableCell className="text-right font-mono">{sec(d.parts[k].avg)}</TableCell>
                <TableCell className="pr-4 text-right font-mono">{sec(d.parts[k].p90)}</TableCell>
              </TableRow>
            ))}
            {!Object.keys(d.parts).length && <TableRow><TableCell colSpan={3} className="pl-4 text-muted-foreground">{t("spNoParts")}</TableCell></TableRow>}
          </TableBody>
        </Table>
      </Panel>

      <div className="grid gap-4 xl:grid-cols-3">
        <SpeedTable title={t("spByStage")} rows={d.by_stage.map((r) => ({ ...r, key: stageLabel(r.stage, t) || r.stage }))} t={t} />
        <SpeedTable title={t("spByKind")} rows={d.by_kind.map((r) => ({ ...r, key: t(r.kind === "photo" ? "spPhoto" : "spText") }))} t={t} />
        <SpeedTable title={t("anGroups")} rows={d.by_group.map((r) => ({ ...r, key: r.group }))} t={t} />
      </div>

      <Panel title={t("spSlow")} hint={t("spSlowHint")} icon={Turtle} bodyClassName="grid gap-2">
        {d.slowest.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
        {d.slowest.map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-2 rounded-lg border px-3 py-2 text-sm">
            <span className="w-14 font-mono font-semibold tabular-nums">{r.secs} s</span>
            {r.photo && <ImageIcon className="size-4 text-muted-foreground" />}
            <span className="min-w-0 flex-1 truncate">{r.text || t("photo")}</span>
            <span className="text-xs text-muted-foreground">{stageLabel(r.stage, t)} · {r.group} · {fmtDate(r.at)}</span>
            <span className="flex w-full flex-wrap gap-1">
              {PART_KEYS.filter((k) => typeof r.timing[k] === "number" && r.timing[k]! > 200).map((k) => (
                <span key={k} className="rounded bg-muted px-1.5 py-px font-mono text-[11px] text-muted-foreground">{t(`sp_${k}` as SKey)} {(r.timing[k]! / 1000).toFixed(1)}s</span>
              ))}
            </span>
          </div>
        ))}
      </Panel>
    </div>
  );
}

function SpeedTable({ title, rows, t }: { title: string; rows: { key: string; n: number; p50: number | null; p90: number | null; max: number }[]; t: ST }) {
  return (
    <Panel title={title} bodyClassName="p-0">
      <Table>
        <TableHeader><TableRow className="bg-muted/40">
          <TableHead className="pl-4">{title}</TableHead><TableHead className="text-right">n</TableHead>
          <TableHead className="text-right">p50</TableHead><TableHead className="pr-4 text-right">p90</TableHead>
        </TableRow></TableHeader>
        <TableBody>
          {rows.length === 0 && <TableRow><TableCell colSpan={4} className="pl-4 text-muted-foreground">{t("empty")}</TableCell></TableRow>}
          {rows.map((r) => (
            <TableRow key={r.key}>
              <TableCell className="max-w-48 truncate pl-4" title={r.key}>{r.key}</TableCell>
              <TableCell className="text-right font-mono">{r.n}</TableCell>
              <TableCell className="text-right font-mono text-xs">{sec(r.p50)}</TableCell>
              <TableCell className="pr-4 text-right font-mono text-xs">{sec(r.p90)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Panel>
  );
}
