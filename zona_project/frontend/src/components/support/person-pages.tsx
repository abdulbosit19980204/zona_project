"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, CircleAlert, CircleCheck, ExternalLink, GraduationCap, HandHelping, Inbox, Star, Tags } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { axisProps, CHART, tooltipStyle } from "@/components/charts/chart-kit";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { supportApi, type AskerDetail, type Insight, type Range } from "./api";
import { fmtDate, fmtDur, Initials, Metric, Panel, Segmented } from "./common";
import { useSt, type SKey, type ST } from "./i18n";
import { Recent, Schedule, StaffHeat } from "./staff";
import { SupportShell } from "./shell";

const PRESETS = ["7", "30", "90", "365", "3650"];
const rangeOf = (p: string): Range => ({ days: Number(p) });

function PeriodPick({ value, onChange, t }: { value: string; onChange: (v: string) => void; t: ST }) {
  return <Segmented size="sm" value={value} onChange={onChange} options={PRESETS.map((x) => ({ value: x, label: t(`ex_p_${x}` as SKey) }))} />;
}

/** Ish holati: 0–100 halqa (yashil ≥75, sariq ≥50, qizil <50) — matn bilan, rang yolg'iz emas. */
function Score({ v, t }: { v: number | null | undefined; t: ST }) {
  if (v == null) return <Metric label={t("pScore")} value="—" />;
  const tone = v >= 75 ? "var(--success)" : v >= 50 ? "var(--warning)" : "var(--destructive)";
  const label = v >= 75 ? t("pScoreGood") : v >= 50 ? t("pScoreMid") : t("pScoreLow");
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-xs">
      <div className="relative size-14 shrink-0 rounded-full" style={{ background: `conic-gradient(${tone} ${v * 3.6}deg, var(--muted) 0)` }}>
        <div className="absolute inset-1.5 grid place-items-center rounded-full bg-card text-sm font-semibold tabular-nums">{v}</div>
      </div>
      <div><div className="text-xs text-muted-foreground">{t("pScore")}</div><div className="font-semibold">{label}</div></div>
    </div>
  );
}

function Stars({ v, n, t }: { v: number | null | undefined; n?: number; t: ST }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border bg-card px-4 py-3 shadow-xs">
      <div>
        <div className="text-xs text-muted-foreground">{t("pRating")}</div>
        <div className="flex items-center gap-0.5" aria-label={v != null ? `${v} / 5` : "—"}>
          {[1, 2, 3, 4, 5].map((i) => <Star key={i} className={`size-4 ${v != null && v >= i - 0.25 ? "fill-warning text-warning" : "text-muted-foreground/40"}`} />)}
          <span className="ml-1.5 text-sm font-semibold tabular-nums">{v != null ? v.toFixed(1) : "—"}</span>
        </div>
        <div className="text-[11px] text-muted-foreground">{t("pRatingN", { n: n ?? 0 })}</div>
      </div>
    </div>
  );
}

const KIND_ICON = { plus: CircleCheck, minus: CircleAlert, train: GraduationCap, help: HandHelping, info: Tags } as const;
const KIND_TONE: Record<string, string> = { plus: "text-success", minus: "text-destructive", train: "text-primary", help: "text-warning", info: "text-muted-foreground" };

function insightText(t: ST, i: Insight) {
  const d = (s?: number | null) => fmtDur(t, s ?? null);
  switch (i.code) {
    case "fast": return t("inFast", { v: d(i.v), team: d(i.team) });
    case "slow": return t("inSlow", { v: d(i.v), team: d(i.team) });
    case "resolve": return t("inResolve", { v: i.v ?? 0 });
    case "rating": return t("inRating", { v: i.v ?? 0, n: i.n ?? 0 });
    case "active": return t("inActive", { v: i.v ?? 0, team: Math.round(i.team ?? 0) });
    case "handoffs": return t("inHandoffs", { v: i.v ?? 0 });
    case "open_old": return t("inOpenOld", { n: i.n ?? 0, v: d((i.v ?? 0) * 3600) });
    case "topic": return t("inTrainTopic", { topic: i.topic ?? "", no: i.no ?? 0, h: i.handoff ?? 0 });
    case "slow_topic": return t("inSlowTopic", { topic: i.topic ?? "", v: d(i.v), n: i.n ?? 0 });
    case "bot_ok": return t("inBotOk", { v: i.v ?? 0 });
    case "unanswered": return t("inUnanswered", { v: i.v ?? 0 });
    case "photo_only": return t("inPhotoOnly", { v: i.v ?? 0 });
    case "repeat": return t("inRepeat", { topic: i.topic ?? "", n: i.n ?? 0 });
    case "unsolved_topic": return t("inUnsolvedTopic", { topic: i.topic ?? "", n: i.n ?? 0 });
    default: return i.code;
  }
}

/** Tavsiyalar to'rt ustunda: kuchli (+), zaif (−), o'rgatish, yordam — har biri belgisi va matni bilan. */
function Insights({ items, t }: { items: Insight[]; t: ST }) {
  const cols: { kind: string; title: SKey }[] = [
    { kind: "plus", title: "pPlus" }, { kind: "minus", title: "pMinus" }, { kind: "train", title: "pTrain" }, { kind: "help", title: "pHelp" }];
  return (
    <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
      {cols.map((c) => {
        const Icon = KIND_ICON[c.kind as keyof typeof KIND_ICON];
        const list = items.filter((i) => i.kind === c.kind || (c.kind === "plus" && i.kind === "info"));
        return (
          <Panel key={c.kind} title={<span className={`inline-flex items-center gap-1.5 ${KIND_TONE[c.kind]}`}><Icon className="size-4" />{t(c.title)}</span>}>
            {list.length === 0 ? <p className="text-sm text-muted-foreground">{t("pNone")}</p> : (
              <ul className="grid gap-2 text-sm">
                {list.map((i, n) => <li key={n} className="leading-snug">{insightText(t, i)}</li>)}
              </ul>
            )}
          </Panel>
        );
      })}
    </div>
  );
}

function Header({ name, sub, back, actions, t }: { name: string; sub: ReactNode; back: string; actions?: ReactNode; t: ST }) {
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Link href={back} className="rounded-lg border p-2 text-muted-foreground hover:bg-muted hover:text-foreground" aria-label={t("pBack")}><ArrowLeft className="size-4" /></Link>
      <Initials name={name} className="size-11" />
      <div className="min-w-0 flex-1">
        <h2 className="truncate text-lg font-semibold">{name}</h2>
        <div className="text-xs text-muted-foreground">{sub}</div>
      </div>
      {actions}
    </div>
  );
}

/* ================================================================ xodim */
export function StaffPage({ id }: { id: number }) {
  const t = useSt();
  const [p, setP] = useState("30");
  const q = useQuery({ queryKey: ["support", "staff-one", id, p], queryFn: () => supportApi.staffOne(id, rangeOf(p)) });
  const d = q.data;
  const ev = d?.eval;
  const me = ev?.me;
  return (
    <SupportShell title={t("pStaffTitle")} description={t("pStaffDesc")} actions={<PeriodPick value={p} onChange={setP} t={t} />}>
      {!d ? <Skeleton className="h-[600px]" /> : (
        <div className="grid gap-4">
          <Header name={d.name} back="/support/analytics" t={t}
            sub={<>{d.from} — {d.to}{d.username && <> · @{d.username}</>}{me?.team && <> · {me.team}</>}</>} />
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
            <Score v={ev?.score} t={t} />
            <Stars v={me?.rating} n={me?.ratings} t={t} />
            <Metric label={t("stMsgs")} value={d.messages} hint={t("anDays", { n: d.active_days })} />
            <Metric label={t("anAnswers")} value={d.answers} hint={`${t("anClar")}: ${d.clarifications}`} />
            <Metric label={t("stHandoffs")} value={d.handoffs} hint={`${t("anReacts")}: ${d.reactions}`} />
            <Metric label={t("anSpeed")} value={fmtDur(t, d.median_s)} hint={`${t("colResolved")}: ${d.resolved}${d.unresolved ? ` / ${d.unresolved}` : ""}`} />
            <Metric label={t("stOpen")} value={me?.open_now ?? 0} hint={me?.oldest_open_h ? t("stOldest", { d: fmtDur(t, me.oldest_open_h * 3600) }) : undefined} tone={me?.open_now ? "warning" : undefined} />
          </div>
          <Insights items={ev?.items ?? []} t={t} />
          <div className="grid gap-4 xl:grid-cols-2">
            <Panel title={t("pDaily")} hint={t("pDailyHint")}>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={d.timeline.map((x) => ({ name: x.date.slice(5), msgs: x.messages, work: x.work }))} margin={{ left: 0, right: 8, top: 8 }}>
                    <CartesianGrid vertical={false} stroke={CHART.grid} strokeDasharray="3 3" />
                    <XAxis dataKey="name" {...axisProps} minTickGap={10} />
                    <YAxis {...axisProps} width={32} allowDecimals={false} />
                    <Tooltip {...tooltipStyle} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Bar dataKey="msgs" name={t("stMsgs")} fill={CHART.muted} radius={[4, 4, 0, 0]} maxBarSize={18} />
                    <Bar dataKey="work" name={t("pWork")} fill={CHART.primary} radius={[4, 4, 0, 0]} maxBarSize={18} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Panel>
            <Panel title={t("pRatingDist")}>
              <RatingDist dist={me?.rating_dist ?? [0, 0, 0, 0, 0]} t={t} />
            </Panel>
          </div>
          <div className="grid gap-4 xl:grid-cols-2">
            <Schedule d={d} t={t} />
            <StaffHeat d={d} t={t} />
          </div>
          <Panel title={t("pTopics")} hint={t("pTopicsHint")} icon={Tags}>
            <TopicTable rows={(ev?.topics ?? []).map((x) => ({ topic: x.topic, n: x.n, bad: x.no, extra: x.handoff, time: x.median_s }))}
              cols={[t("pTopic"), t("ex_m_questions"), t("ex_m_no"), t("stHandoffs"), t("anSpeed")]} t={t} />
          </Panel>
          <Recent d={d} t={t} />
        </div>
      )}
    </SupportShell>
  );
}

function RatingDist({ dist, t }: { dist: number[]; t: ST }) {
  const max = Math.max(1, ...dist);
  const total = dist.reduce((a, b) => a + b, 0);
  if (!total) return <p className="text-sm text-muted-foreground">{t("pNoRatings")}</p>;
  return (
    <div className="grid gap-2">
      {[5, 4, 3, 2, 1].map((s) => (
        <div key={s} className="grid grid-cols-[48px_1fr_36px] items-center gap-2 text-sm">
          <span className="tabular-nums">{s} ⭐</span>
          <div className="h-2.5 rounded-full bg-muted"><div className="h-2.5 rounded-full bg-warning" style={{ width: `${(100 * dist[s - 1]) / max}%` }} /></div>
          <span className="text-right font-mono text-xs tabular-nums">{dist[s - 1]}</span>
        </div>
      ))}
    </div>
  );
}

function TopicTable({ rows, cols, t }: { rows: { topic: string; n: number; bad: number; extra: number; time?: number | null }[]; cols: string[]; t: ST }) {
  if (!rows.length) return <p className="text-sm text-muted-foreground">{t("empty")}</p>;
  const max = Math.max(1, ...rows.map((r) => r.n));
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[560px] text-sm">
        <thead><tr className="text-left text-xs text-muted-foreground">{cols.map((c, i) => <th key={c} className={`pb-2 font-medium ${i ? "text-right" : ""}`}>{c}</th>)}</tr></thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.topic} className="border-t">
              <td className="py-1.5 pr-3"><div className="truncate">{r.topic}</div>
                <div className="mt-1 h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${(100 * r.n) / max}%` }} /></div></td>
              <td className="text-right font-mono tabular-nums">{r.n}</td>
              <td className={`text-right font-mono tabular-nums ${r.bad ? "text-destructive" : ""}`}>{r.bad}</td>
              <td className="text-right font-mono tabular-nums">{r.extra}</td>
              {cols.length > 4 && <td className="text-right font-mono text-xs tabular-nums">{fmtDur(t, r.time ?? null)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/* ================================================================ agent */
export function AskerPage({ id }: { id: number }) {
  const t = useSt();
  const [p, setP] = useState("30");
  const q = useQuery({ queryKey: ["support", "asker-one", id, p], queryFn: () => supportApi.askerOne(id, rangeOf(p)) });
  const d = q.data;
  return (
    <SupportShell title={t("pAskerTitle")} description={t("pAskerDesc")} actions={<PeriodPick value={p} onChange={setP} t={t} />}>
      {!d ? <Skeleton className="h-[600px]" /> : <AskerBody d={d} t={t} days={p} />}
    </SupportShell>
  );
}

function AskerBody({ d, t, days }: { d: AskerDetail; t: ST; days: string }) {
  const m = d.metrics;
  const w = d.who;
  const inbox = `/support?${new URLSearchParams({ ex: "1", scope: "all", f_asker: String(d.id), days }).toString()}`;
  return (
    <div className="grid gap-4">
      <Header name={w.name || "—"} back="/support/analytics" t={t}
        sub={[w.role, w.project, w.territory, w.supervisor && `${t("pSupervisor")}: ${w.supervisor}`, w.username && "@" + w.username, w.phone].filter(Boolean).join(" · ")}
        actions={<Link href={inbox} className="inline-flex items-center gap-1 rounded-lg border px-3 py-1.5 text-sm text-primary hover:bg-muted"><Inbox className="size-4" />{t("exQuestionsList")}</Link>} />
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
        <Metric label={t("ex_m_count")} value={m.count ?? 0} tone="primary" />
        <Metric label={t("ex_m_bot")} value={m.bot ?? 0} hint={m.bot_share != null ? `${m.bot_share}%` : undefined} tone="success" />
        <Metric label={t("ex_m_staff")} value={m.staff ?? 0} />
        <Metric label={t("ex_m_unanswered")} value={m.unanswered ?? 0} tone={m.unanswered ? "warning" : undefined} />
        <Metric label={t("ex_m_rate")} value={m.rate != null ? `${m.rate}%` : "—"} hint={`${t("ex_m_yes")} ${m.yes ?? 0} · ${t("ex_m_no")} ${m.no ?? 0}`} />
        <Metric label={t("ex_m_median_s")} value={fmtDur(t, m.median_s ?? null)} />
        <Metric label={t("ex_m_open")} value={m.open ?? 0} />
      </div>
      <Insights items={d.insights} t={t} />
      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("exByDay")}>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={d.daily.map((x) => ({ name: x.date.slice(5), n: x.n }))} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} stroke={CHART.grid} strokeDasharray="3 3" />
                <XAxis dataKey="name" {...axisProps} minTickGap={10} />
                <YAxis {...axisProps} width={28} allowDecimals={false} />
                <Tooltip {...tooltipStyle} />
                <Bar dataKey="n" name={t("ex_m_count")} fill={CHART.primary} radius={[4, 4, 0, 0]} maxBarSize={18} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
        <Panel title={t("pHours")}>
          <div className="h-56">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={d.hours.map((n, h) => ({ name: `${h}`, n }))} margin={{ left: 0, right: 8, top: 8 }}>
                <CartesianGrid vertical={false} stroke={CHART.grid} strokeDasharray="3 3" />
                <XAxis dataKey="name" {...axisProps} interval={2} />
                <YAxis {...axisProps} width={28} allowDecimals={false} />
                <Tooltip {...tooltipStyle} labelFormatter={(h) => `${h}:00`} />
                <Bar dataKey="n" name={t("ex_m_count")} fill={CHART.violet} radius={[4, 4, 0, 0]} maxBarSize={14} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </Panel>
      </div>
      <div className="grid gap-4 xl:grid-cols-[2fr_1fr]">
        <Panel title={t("pTopics")} icon={Tags}>
          <TopicTable rows={d.topics.map((x) => ({ topic: x.topic, n: x.n, bad: x.no + x.unanswered, extra: x.bot }))}
            cols={[t("pTopic"), t("ex_m_questions"), t("pUnsolved"), t("ex_m_bot")]} t={t} />
        </Panel>
        <Panel title={t("exWhoAnswered")}>
          {d.staff.length === 0 ? <p className="text-sm text-muted-foreground">{t("empty")}</p> : (
            <div className="grid gap-1.5">{d.staff.map((s) => (
              <div key={s.name} className="flex items-center justify-between gap-2 text-sm"><span className="truncate">{s.name}</span><Badge variant="outline">{s.n}</Badge></div>
            ))}</div>
          )}
        </Panel>
      </div>
      <Panel title={t("pRecentQ")}>
        <div className="grid max-h-[520px] gap-2 overflow-y-auto pr-1">
          {d.recent.map((r) => (
            <div key={r.id} className="flex items-start gap-3 rounded-lg border p-2.5 text-sm">
              <div className="min-w-0 flex-1">
                <div className="mb-1 flex flex-wrap gap-2 text-[11px] text-muted-foreground">
                  <span className="tabular-nums">{fmtDate(r.at)}</span><span>{r.group}</span>
                  <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-normal">{t(`m_${r.status}` as SKey)}</Badge>
                  {r.resolution && <Badge variant="outline" className="h-5 px-1.5 text-[10px] font-normal">{t(`r_${r.resolution}` as SKey)}</Badge>}
                </div>
                <div className="line-clamp-2">{r.text || (r.photo ? t("photo") : "—")}</div>
              </div>
              <div className="flex shrink-0 flex-col gap-1 text-xs">
                <Link href={`/support?q=${r.id}`} className="text-primary hover:underline">{t("exOpen")}</Link>
                {r.link && <a href={r.link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline"><ExternalLink className="size-3" />TG</a>}
              </div>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}
