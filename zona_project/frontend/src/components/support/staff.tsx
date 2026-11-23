"use client";

import { useQuery } from "@tanstack/react-query";
import { CalendarDays, ExternalLink, History, MessageSquare, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { supportApi, type Range, type StaffBoardRow, type StaffDetail } from "./api";
import { fmtDate, fmtDur, Initials, Metric, Panel } from "./common";
import { DataTable, type Column } from "./data-table";
import type { SKey, ST } from "./i18n";

const WD: SKey[] = ["wd0", "wd1", "wd2", "wd3", "wd4", "wd5", "wd6"];
const shade = (v: number, max: number) => (v ? `color-mix(in oklab, var(--primary) ${Math.round(12 + 88 * (v / max))}%, var(--card))` : undefined);

/** Xodimlar: guruhdagi xabarlari, ish vaqti, nima qilgani va tezligi; qatorni bosib — to'liq ish grafigi. */
export function StaffBoard({ range, t }: { range: Range; t: ST }) {
  const q = useQuery({ queryKey: ["support", "staff-board", range], queryFn: () => supportApi.staffBoard(range) });
  const d = q.data;
  if (!d) return <Skeleton className="h-96" />;
  const columns: Column<StaffBoardRow>[] = [
    { key: "name", header: t("staff"), sort: (s) => s.name.toLowerCase(), cell: (s) => (
      <Link href={`/support/staff/${s.id}`} className="flex min-w-48 items-center gap-2.5 text-left hover:underline">
        <Initials name={s.name} className="size-8" />
        <span className="min-w-0">
          <span className="block font-medium">{s.name}</span>
          <span className="block max-w-64 truncate text-[11px] text-muted-foreground">
            {[s.team, s.username && "@" + s.username].filter(Boolean).join(" · ")}
          </span>
        </span>
      </Link>
    ) },
    { key: "msgs", header: t("stMsgs"), align: "right", sort: (s) => s.messages, cell: (s) => <span className="font-mono">{s.messages}</span> },
    { key: "days", header: t("stDays"), align: "right", sort: (s) => s.active_days, cell: (s) => <span className="font-mono">{s.active_days}</span> },
    { key: "hours", header: t("stHours"), sort: (s) => s.span_h, cell: (s) => (
      s.start ? <span className="font-mono text-xs">{s.start}–{s.end}<span className="block text-muted-foreground">⌀ {t("wlHours", { n: s.span_h })}</span></span>
        : <span className="text-muted-foreground">—</span>
    ) },
    { key: "answers", header: t("anAnswers"), align: "right", sort: (s) => s.answers, cell: (s) => <span className="font-mono">{s.answers}</span> },
    { key: "clar", header: t("anClar"), align: "right", sort: (s) => s.clarifications, cell: (s) => <span className="font-mono">{s.clarifications}</span> },
    { key: "hand", header: t("stHandoffs"), align: "right", sort: (s) => s.handoffs, cell: (s) => <span className="font-mono">{s.handoffs}</span> },
    { key: "react", header: t("anReacts"), align: "right", sort: (s) => s.reactions, cell: (s) => (
      <span className="font-mono">{s.reactions}{s.working > 0 && <span className="block text-[11px] text-primary">{t("anWorking")}: {s.working}</span>}</span>
    ) },
    { key: "res", header: t("colResolved"), align: "right", sort: (s) => s.resolved, cell: (s) => (
      <span className="font-mono"><span className="text-success">{s.resolved}</span>
        {s.unresolved > 0 && <span className="text-destructive"> / {s.unresolved}</span>}
        {s.closed > 0 && <span className="block text-[11px] text-muted-foreground">{t("stClosed", { n: s.closed })}</span>}</span>
    ) },
    { key: "open", header: t("stOpen"), align: "right", sort: (s) => s.open_now ?? 0, cell: (s) => (
      s.open_now ? <span className="font-mono"><span className={(s.oldest_open_h ?? 0) >= 24 ? "text-destructive" : "text-warning"}>{s.open_now}</span>
        <span className="block text-[11px] text-muted-foreground">{t("stOldest", { d: fmtDur(t, (s.oldest_open_h ?? 0) * 3600) })}</span></span>
        : <span className="text-muted-foreground">0</span>
    ) },
    { key: "speed", header: t("anSpeed"), align: "right", sort: (s) => s.median_s ?? 1e12, cell: (s) => <span className="font-mono text-xs">{fmtDur(t, s.median_s)}</span> },
    { key: "seen", header: t("stLastSeen"), align: "right", sort: (s) => s.last_seen ?? "", cell: (s) => (
      <span className="text-xs tabular-nums text-muted-foreground">{s.last_seen ? fmtDate(s.last_seen) : "—"}</span>
    ) },
  ];
  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-5">
        <Metric label={t("stActive")} value={d.totals.staff} icon={Users} tone="primary" />
        <Metric label={t("stMsgs")} value={d.totals.messages} icon={MessageSquare} />
        <Metric label={t("anAnswers")} value={d.totals.answers} icon={UserRound} tone="success" />
        <Metric label={t("anClar")} value={d.totals.clarifications} />
        <Metric label={t("stHandoffs")} value={d.totals.handoffs} />
      </div>
      <Panel title={t("anStaff")} hint={t("stHint")} icon={UserRound}>
        <DataTable rows={d.staff} columns={columns} rowKey={(s) => s.id} t={t} initialSort={{ key: "msgs", dir: "desc" }}
          search={(s) => [s.name, s.username, s.team, ...s.groups.map((g) => g.title)].join(" ")}
          filters={[{ value: "active", label: t("stOnlyActive"), test: (s) => s.messages + s.answers > 0 },
            { value: "all", label: t("dtAll"), test: () => true }]} />
      </Panel>

    </div>
  );
}

/** Ish grafigi: har kun — birinchi va oxirgi xabar orasidagi oraliq 0–24 soat shkalasida, xabarlar soni bilan. */
export function Schedule({ d, t }: { d: StaffDetail; t: ST }) {
  const days = [...d.timeline].reverse();
  return (
    <Panel title={t("stSchedule")} hint={t("stScheduleHint")} icon={CalendarDays}>
      {days.length === 0 ? <p className="text-sm text-muted-foreground">{t("empty")}</p> : (
        <div className="grid max-h-[420px] gap-1 overflow-y-auto pr-1">
          <div className="grid grid-cols-[86px_1fr_120px] items-end gap-2 text-[10px] text-muted-foreground">
            <span />
            <div className="relative h-3">
              {[0, 6, 12, 18, 24].map((h) => (
                <span key={h} className={`absolute tabular-nums ${h === 0 ? "" : h === 24 ? "-translate-x-full" : "-translate-x-1/2"}`}
                  style={{ left: `${(100 * h) / 24}%` }}>{String(h).padStart(2, "0")}:00</span>
              ))}
            </div>
            <span />
          </div>
          {days.map((x) => (
            <div key={x.date} className="grid grid-cols-[86px_1fr_120px] items-center gap-2 text-xs"
              title={`${x.date}: ${x.first}–${x.last} · ${t("stMsgsN", { n: x.messages })} · ${t("stWorkN", { n: x.work })}`}>
              <span className="tabular-nums text-muted-foreground">{x.date.slice(5)} {t(WD[x.weekday])}</span>
              <div className="relative h-4 rounded bg-muted/60">
                {[9, 18].map((h) => <span key={h} className="absolute inset-y-0 w-px bg-border" style={{ left: `${(100 * h) / 24}%` }} />)}
                <span className="absolute inset-y-0.5 rounded-sm bg-primary/70"
                  style={{ left: `${(100 * x.first_m) / 1440}%`, width: `max(3px, ${(100 * Math.max(0, x.last_m - x.first_m)) / 1440}%)` }} />
              </div>
              <span className="font-mono tabular-nums">{x.first}–{x.last}
                <span className="text-muted-foreground"> · {x.messages}</span></span>
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}

export function StaffHeat({ d, t }: { d: StaffDetail; t: ST }) {
  const max = Math.max(1, ...d.heatmap.flat());
  const [hover, setHover] = useState<{ wd: number; h: number } | null>(null);
  return (
    <Panel title={t("stHeat")} hint={t("stHeatHint")} icon={History}>
      <div className="overflow-x-auto">
        <div className="grid min-w-[520px] gap-[2px]" style={{ gridTemplateColumns: "28px repeat(24, minmax(0, 1fr))" }}
          onMouseLeave={() => setHover(null)}>
          <span />
          {Array.from({ length: 24 }, (_, h) => <span key={h} className="text-center text-[10px] tabular-nums text-muted-foreground">{h % 3 === 0 ? h : ""}</span>)}
          {d.heatmap.map((row, wd) => (
            <div key={wd} className="contents">
              <span className="self-center text-[11px] text-muted-foreground">{t(WD[wd])}</span>
              {row.map((v, h) => (
                <button key={h} type="button" aria-label={`${t(WD[wd])} ${h}:00 — ${v}`} onMouseEnter={() => setHover({ wd, h })}
                  onFocus={() => setHover({ wd, h })}
                  className={`aspect-square rounded-[3px] outline-none focus-visible:ring-2 focus-visible:ring-ring ${v ? "" : "bg-muted/60"} ${hover?.wd === wd && hover?.h === h ? "ring-2 ring-foreground/60" : ""}`}
                  style={{ background: shade(v, max) }} />
              ))}
            </div>
          ))}
        </div>
      </div>
      <p className="mt-2 min-h-4 text-xs text-muted-foreground">
        {hover && <><b className="text-foreground">{t(WD[hover.wd])} {String(hover.h).padStart(2, "0")}:00</b> · {t("stMsgsN", { n: d.heatmap[hover.wd][hover.h] })}</>}
      </p>
    </Panel>
  );
}

const KIND: Record<string, SKey> = { staff: "stK_staff", clarify: "stK_clarify", info: "stK_info", feedback: "stK_feedback", other: "stK_other" };

export function Recent({ d, t }: { d: StaffDetail; t: ST }) {
  return (
    <Panel title={t("stRecent")} hint={t("stRecentHint")} icon={MessageSquare}>
      {d.recent.length === 0 ? <p className="text-sm text-muted-foreground">{t("empty")}</p> : (
        <div className="grid max-h-[520px] gap-2 overflow-y-auto pr-1">
          {d.recent.map((r) => (
            <div key={r.id} className="rounded-lg border p-2.5 text-sm">
              <div className="mb-1 flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
                <span className="tabular-nums">{fmtDate(r.at)}</span>
                <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-normal">{t(KIND[r.kind] ?? "stK_other")}</Badge>
                <span className="truncate">{r.group}</span>
                {r.link && <a href={r.link} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-primary hover:underline">
                  <ExternalLink className="size-3" />Telegram</a>}
              </div>
              <div className="whitespace-pre-wrap leading-snug">{r.text || "—"}</div>
              {r.question && <div className="mt-1 line-clamp-2 border-l-2 pl-2 text-xs text-muted-foreground">{r.question}</div>}
            </div>
          ))}
        </div>
      )}
    </Panel>
  );
}
