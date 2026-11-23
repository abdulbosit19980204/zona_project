"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Bot, CircleCheck, Clock3, Zap, HelpCircle, Image as ImageIcon, Inbox, ListChecks, MessageCircleQuestion, Tags, Target, UserRound, Users } from "lucide-react";
import Link from "next/link";
import { useState, type ReactNode } from "react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

import { supportApi, type Analytics, type Range } from "./api";
import { Input } from "@/components/ui/input";

import { fmtDur, Initials, Metric, Panel, Segmented, stageLabel } from "./common";
import { DataTable, type Column } from "./data-table";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";
import { Speed } from "./speed";
import { Workload } from "./workload";

type Tab = "overview" | "speed" | "workload" | "staff" | "askers" | "topics";

/** Tahlil: savollar, bot ishi, xodimlar javoblari va javobdan oldin so'raladigan ma'lumotlar — bo'limlarga ajratilgan. */
export function SupportAnalytics() {
  const t = useSt();
  const [preset, setPreset] = useState("30");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [tab, setTab] = useState<Tab>("overview");
  const range: Range = preset === "custom" ? { from: from || to, to: to || from } : { days: Number(preset) };
  const ready = preset !== "custom" || Boolean(from || to);
  const q = useQuery({ queryKey: ["support", "analytics", range], queryFn: () => supportApi.analytics(range), refetchInterval: 60_000, enabled: ready });
  const a = q.data;
  const sm = a?.summary;

  return (
    <SupportShell title={t("anTitle")} description={t("anDesc")}
      actions={
        <div className="flex flex-wrap items-center justify-end gap-2">
          <Segmented size="sm" value={preset} onChange={setPreset} options={[
            { value: "1", label: t("daysToday") }, { value: "7", label: t("days7") }, { value: "30", label: t("days30") },
            { value: "90", label: t("days90") }, { value: "custom", label: t("daysCustom") },
          ]} />
          {preset === "custom" && (
            <div className="flex items-center gap-1.5">
              <Input type="date" value={from} max={to || undefined} onChange={(e) => setFrom(e.target.value)} className="h-8 w-36 text-xs" aria-label={t("dateFrom")} />
              <span className="text-xs text-muted-foreground">—</span>
              <Input type="date" value={to} min={from || undefined} onChange={(e) => setTo(e.target.value)} className="h-8 w-36 text-xs" aria-label={t("dateTo")} />
            </div>
          )}
          {a && <span className="text-[11px] tabular-nums text-muted-foreground">{a.from === a.to ? a.from : `${a.from} — ${a.to}`} · GMT+5</span>}
        </div>
      }>
      {!a && <div className="grid gap-4"><Skeleton className="h-20" /><Skeleton className="h-96" /></div>}
      {a && (
        <div className="grid gap-5">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
            <Drill to="total" range={range}><Metric label={t("anQuestions")} value={a.questions} hint={`${t("anPhoto")}: ${a.with_photo}`} icon={Inbox} tone="primary" /></Drill>
            <Drill to="yes" range={range}><Metric label={t("resRate")} value={a.resolution?.rate != null ? `${a.resolution.rate}%` : "—"}
              hint={a.resolution ? `${t("r_yes")} ${a.resolution.yes} · ${t("r_no")} ${a.resolution.no}` : undefined} icon={CircleCheck} tone="success" /></Drill>
            <Drill to="bot" range={range}><Metric label={t("kpiBot")} value={sm?.bot ?? 0} hint={sm?.bot_share != null ? `${sm.bot_share}%` : undefined} icon={Bot} tone="success" /></Drill>
            <Drill to="staff" range={range}><Metric label={t("kpiStaff")} value={sm?.staff ?? 0}
              hint={sm ? `${sm.staff_share ?? 0}% · ${t("kpiReacts", { n: sm.react })}` : undefined} icon={UserRound} /></Drill>
            <Drill to="unanswered" range={range}><Metric label={t("anUnanswered")} value={sm?.unanswered ?? a.unanswered} icon={HelpCircle} tone="warning" /></Drill>
            <Drill to="open" range={range}><Metric label={t("anOpenNow")} value={sm?.open ?? 0} hint={t("anOpenHint")} icon={ListChecks} tone="warning" /></Drill>
          </div>
          <Scope a={a} t={t} />

          <Segmented value={tab} onChange={setTab} options={[
            { value: "overview", label: t("anTabOverview"), icon: BarChart3 },
            { value: "speed", label: t("anTabSpeed"), icon: Zap },
            { value: "workload", label: t("anTabWorkload"), icon: Clock3 },
            { value: "staff", label: t("anTabStaff"), icon: UserRound, count: a.staff.length },
            { value: "askers", label: t("anTabAskers"), icon: Users, count: a.askers.length },
            { value: "topics", label: t("anTabTopics"), icon: Tags },
          ]} />

          {tab === "overview" && <Overview a={a} t={t} range={range} />}
          {tab === "speed" && <Speed range={range} t={t} />}
          {tab === "workload" && <Workload range={range} t={t} />}
          {tab === "staff" && <StaffTable a={a} t={t} />}
          {tab === "askers" && <Askers a={a} t={t} />}
          {tab === "topics" && <Topics a={a} t={t} />}
        </div>
      )}
    </SupportShell>
  );
}

function Bars({ rows, empty }: { rows: { key: string; label: string; n: number }[]; empty: string }) {
  const max = Math.max(1, ...rows.map((r) => r.n));
  if (!rows.length) return <p className="text-sm text-muted-foreground">{empty}</p>;
  return (
    <div className="grid gap-2.5">
      {rows.map((r) => (
        <div key={r.key} className="grid gap-1 text-sm">
          <div className="flex justify-between gap-3"><span className="truncate" title={r.label}>{r.label}</span><span className="font-mono text-xs tabular-nums text-muted-foreground">{r.n}</span></div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-primary" style={{ width: `${(100 * r.n) / max}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-lg bg-muted/50 px-3 py-2">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="font-semibold tabular-nums">{value}</div>
    </div>
  );
}

/** Statistikaga nima kiradi: faqat jonli savollar va tahlilga qo'shilgan guruhlar; nimalar chiqarib tashlangani. */
function Scope({ a, t }: { a: Analytics; t: ST }) {
  const x = a.excluded;
  if (!x) return null;
  const parts = [
    x.history > 0 && t("anExHistory", { n: x.history }),
    x.groups_off > 0 && `${t("anExGroups", { n: x.groups_off })}${x.groups.length ? ` (${x.groups.join(", ")})` : ""}`,
    x.duplicates > 0 && t("anExDup", { n: x.duplicates }),
    x.ignored > 0 && t("anExIgnored", { n: x.ignored }),
  ].filter(Boolean) as string[];
  return (
    <p className="-mt-2 flex flex-wrap items-center gap-x-1.5 text-xs text-muted-foreground">
      <span>{t("anScope")}</span>
      {parts.length > 0 && <span>— {parts.join(" · ")}.</span>}
      <Link href="/support/settings?tab=groups" className="font-medium text-primary hover:underline">{t("anScopeEdit")}</Link>
    </p>
  );
}

/** Tahlildagi raqam -> «Savollar» sahifasida aynan shu savollar (o'sha davr va tahlil doirasi bilan). */
export function drillHref(to: string, range: Range) {
  const p = new URLSearchParams({ drill: to });
  if ("days" in range && range.days) p.set("days", String(range.days));
  if ("from" in range && range.from) p.set("from", range.from);
  if ("to" in range && range.to) p.set("to", range.to);
  return `/support?${p.toString()}`;
}

function Drill({ to, range, children }: { to: string; range: Range; children: ReactNode }) {
  return (
    <Link href={drillHref(to, range)}
      className="rounded-xl outline-none transition-transform hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-ring">
      {children}
    </Link>
  );
}

/** Savollar yakuni: hal bo'ldi / hal bo'lmadi / jarayonda / tasdiq kutilmoqda / noma'lum — bitta ulushli chiziq va raqamlar. */
function Outcomes({ a, t, range }: { a: Analytics; t: ST; range: Range }) {
  const r = a.resolution;
  if (!r) return null;
  const parts = [
    { key: "yes", n: r.yes, cls: "bg-success", label: t("r_yes") },
    { key: "no", n: r.no, cls: "bg-destructive", label: t("r_no") },
    { key: "work", n: r.work ?? 0, cls: "bg-primary/70", label: t("r_work") },
    { key: "asked", n: r.asked, cls: "bg-warning", label: t("r_asked") },
    { key: "unknown", n: r.unknown, cls: "bg-muted-foreground/25", label: t("r_") },
  ];
  const total = Math.max(1, r.total);
  return (
    <Panel title={t("resTitle")} icon={CircleCheck}>
      <p className="mb-3 text-xs text-muted-foreground">{t("resHint")}</p>
      <div className="flex h-3 w-full gap-0.5 overflow-hidden rounded-full bg-muted" role="img"
        aria-label={parts.map((p) => `${p.label}: ${p.n}`).join(", ")}>
        {parts.filter((p) => p.n > 0).map((p) => (
          <div key={p.key} className={p.cls} style={{ width: `${(100 * p.n) / total}%` }} title={`${p.label}: ${p.n}`} />
        ))}
      </div>
      <div className="mt-3 grid grid-cols-2 gap-2 sm:grid-cols-5">
        {parts.map((p) => (
          <Link key={p.key} href={drillHref(p.key, range)} title={t("anDrill")}
            className="flex items-center gap-2 rounded-lg bg-muted/50 px-3 py-2 transition-colors hover:bg-muted">
            <span className={`size-2.5 shrink-0 rounded-sm ${p.cls}`} />
            <span className="min-w-0 flex-1 truncate text-xs text-muted-foreground">{p.label}</span>
            <span className="font-semibold tabular-nums">{p.n}</span>
            <span className="text-[11px] tabular-nums text-muted-foreground">{Math.round((100 * p.n) / total)}%</span>
          </Link>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>{t("resRate")}: <b className="text-foreground tabular-nums">{r.rate != null ? `${r.rate}%` : "—"}</b> ({t("resRateHint")})</span>
        <span>{t("resConfirmed")}: <b className="text-foreground tabular-nums">{r.confirmed_share != null ? `${r.confirmed_share}%` : "—"}</b></span>
        {r.by.length > 0 && <span>{t("resBy")}: {r.by.map((b) => `${b.by} (${b.n})`).join(", ")}</span>}
      </div>
    </Panel>
  );
}

/** Qaysi guruh qaysi tizim bilan ishlaydi, xatolar qayerda ko'rinadi va qayerdan chiqadi; o'qitish ma'lumoti. */
function Systems({ a, t }: { a: Analytics; t: ST }) {
  const s = a.systems;
  const [busy, setBusy] = useState(false);
  if (!s || !s.total) return null;
  const sys = (k: string) => t(`sys_${k}` as SKey);
  const org = (k: string) => t(`org_${k}` as SKey);
  const cat = (k: string) => t(`cat_${k}` as SKey);
  const chips = (m: Record<string, number>, lbl: (k: string) => string) =>
    Object.entries(m).sort((x, y) => y[1] - x[1]).map(([k, n]) => (
      <Badge key={k} variant="outline" className="mr-1 mb-1 font-normal">{lbl(k)} <b className="ml-1 tabular-nums">{n}</b></Badge>));
  const download = async () => {
    setBusy(true);
    try {
      const blob = await supportApi.trainingFile();
      const url = URL.createObjectURL(blob);
      const el = document.createElement("a");
      el.href = url;
      el.download = `support-training-${new Date().toISOString().slice(0, 10)}.jsonl`;
      el.click();
      URL.revokeObjectURL(url);
    } finally {
      setBusy(false);
    }
  };
  const lab = s.labeled;
  return (
    <Panel title={t("sysTitle")} icon={Target}
      actions={<button className="text-xs font-medium text-primary hover:underline disabled:opacity-50" disabled={busy}
        onClick={download}>{t("sysExport")}</button>}>
      <p className="mb-3 text-xs text-muted-foreground">{t("sysHint")}</p>
      <div className="mb-3 grid gap-2 sm:grid-cols-2">
        <div><div className="mb-1 text-xs text-muted-foreground">{t("sysApps")}</div>{chips(s.apps, sys)}</div>
        <div><div className="mb-1 text-xs text-muted-foreground">{t("sysOrigins")}</div>{chips(s.origins, org)}</div>
      </div>
      {s.pairs.length > 0 && (
        <div className="mb-3">
          <div className="mb-1 text-xs text-muted-foreground">{t("sysPairs")}</div>
          {s.pairs.map((p) => (
            <Badge key={`${p.app}-${p.origin}`} variant="outline" className="mr-1 mb-1 font-normal">
              {sys(p.app)} → {org(p.origin)} <b className="ml-1 tabular-nums">{p.n}</b>
            </Badge>
          ))}
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-xs text-muted-foreground">
            <tr className="border-b text-left">
              <th className="py-1.5 pr-2 font-medium">{t("sysGroup")}</th>
              <th className="py-1.5 pr-2 text-right font-medium">{t("sysQuestions")}</th>
              <th className="py-1.5 pr-2 font-medium">{t("sysApps")}</th>
              <th className="py-1.5 pr-2 font-medium">{t("sysOrigins")}</th>
              <th className="py-1.5 pr-2 font-medium">{t("sysTop")}</th>
              <th className="py-1.5 text-right font-medium">{t("r_yes")}</th>
            </tr>
          </thead>
          <tbody>
            {s.groups.map((g) => (
              <tr key={g.title} className="border-b align-top last:border-0">
                <td className="py-1.5 pr-2 font-medium">{g.title}</td>
                <td className="py-1.5 pr-2 text-right tabular-nums">{g.total}</td>
                <td className="py-1.5 pr-2">{chips(g.apps, sys)}</td>
                <td className="py-1.5 pr-2">{chips(g.origins, org)}</td>
                <td className="py-1.5 pr-2 text-xs">{g.top.map((c) => `${cat(c.category)} (${c.n})`).join(", ")}</td>
                <td className="py-1.5 text-right tabular-nums">{g.resolved}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex flex-wrap gap-x-6 gap-y-1 text-xs text-muted-foreground">
        <span>{t("sysLabeledAi")}: <b className="text-foreground tabular-nums">{lab.ai ?? 0}</b></span>
        <span>{t("sysLabeledStaff")}: <b className="text-foreground tabular-nums">{lab.staff ?? 0}</b></span>
        <span>{t("sysLabeledRule")}: <b className="text-foreground tabular-nums">{lab.rule ?? 0}</b></span>
        <span>{t("sysUnlabeled")}: <b className="text-foreground tabular-nums">{lab.none ?? 0}</b></span>
        <span>{t("sysTrain")}: <b className="text-foreground tabular-nums">{s.train}</b></span>
      </div>
    </Panel>
  );
}

function Overview({ a, t, range }: { a: Analytics; t: ST; range: Range }) {
  const maxDay = Math.max(1, ...a.daily.map((d) => d.total));
  return (
    <div className="grid gap-4">
      <Outcomes a={a} t={t} range={range} />
      <Systems a={a} t={t} />
      <Panel title={t("anDaily")} icon={BarChart3}
        actions={(
          <div className="hidden flex-wrap gap-3 text-xs text-muted-foreground sm:flex">
            <span className="inline-flex items-center gap-1"><span className="size-2 rounded-sm bg-primary" />{t("kpiBot")}</span>
            <span className="inline-flex items-center gap-1"><span className="size-2 rounded-sm bg-success/70" />{t("staffAnswers")}</span>
            <span className="inline-flex items-center gap-1"><span className="size-2 rounded-sm bg-primary/25" />{t("anUnanswered")}</span>
          </div>
        )}>
        {a.daily.length === 0 ? <p className="text-sm text-muted-foreground">{t("empty")}</p> : (
          <>
            <div className="flex h-44 items-end gap-[3px] overflow-x-auto border-b">
              {a.daily.map((d) => (
                <div key={d.date} className="group relative flex h-full min-w-2.5 flex-1 flex-col justify-end" title={`${d.date}: ${d.total} (bot ${d.bot}, ${d.staff})`}>
                  <div className="rounded-t-sm bg-primary/25" style={{ height: `${(100 * Math.max(0, d.total - d.bot - d.staff)) / maxDay}%` }} />
                  <div className="bg-success/70" style={{ height: `${(100 * d.staff) / maxDay}%` }} />
                  <div className="bg-primary group-hover:bg-primary/80" style={{ height: `${(100 * d.bot) / maxDay}%` }} />
                </div>
              ))}
            </div>
            <div className="mt-1.5 flex justify-between text-[11px] tabular-nums text-muted-foreground">
              <span>{a.daily[0]?.date}</span><span>{a.daily[a.daily.length - 1]?.date}</span>
            </div>
          </>
        )}
      </Panel>

      <div className="grid gap-4 lg:grid-cols-3">
        <Panel title={t("anGroups")} icon={Users}>
          <Bars rows={a.groups.map((g) => ({ key: g.title, label: g.title, n: g.n }))} empty={t("empty")} />
        </Panel>
        <Panel title={t("anPt")} icon={Target}>
          <div className="mb-3 grid grid-cols-2 gap-2">
            <Stat label={t("anQuestions")} value={a.protarget.questions} />
            <Stat label={t("kpiBot")} value={a.protarget.by_bot} />
            <Stat label={t("anUnanswered")} value={a.protarget.unanswered} />
            <Stat label={t("anPtTeam")} value={<>{a.protarget.team_answers}{a.protarget.team_median_s != null && <span className="text-xs font-normal text-muted-foreground"> · {fmtDur(t, a.protarget.team_median_s)}</span>}</>} />
          </div>
          <Bars rows={a.protarget.types.map((x) => ({ key: x.title, label: x.title, n: x.n }))} empty={t("empty")} />
        </Panel>
        <Panel title={t("anImages")} icon={ImageIcon}>
          <div className="mb-3 grid grid-cols-2 gap-2">
            <Stat label={t("anImgTotal")} value={a.images.total} />
            <Stat label={t("anImgLabeled")} value={a.images.labeled} />
            <Stat label={t("anImgTypes")} value={a.images.types} />
            <Stat label={t("anImgByImage")} value={a.images.by_image} />
          </div>
          <Bars rows={Object.entries(a.zones).sort((x, y) => y[1] - x[1]).map(([z, n]) => ({ key: z, label: z, n }))} empty={t("empty")} />
        </Panel>
      </div>

      <Panel title={t("anHow")} icon={Bot}>
        <div className="flex flex-wrap gap-2 text-xs">
          {Object.entries(a.by_stage).map(([k, v]) => (
            <Badge key={k} variant="outline" className="gap-1.5 font-normal">{stageLabel(k, t) || k}<span className="font-mono font-semibold">{v}</span></Badge>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function StaffTable({ a, t }: { a: Analytics; t: ST }) {
  type R = Analytics["staff"][number];
  const columns: Column<R>[] = [
    { key: "name", header: t("staff"), sort: (s) => s.name.toLowerCase(), cell: (s) => (
      <div className="flex min-w-52 items-center gap-2.5">
        <Initials name={s.name} className="size-8" />
        <div className="min-w-0">
          <div className="font-medium">{s.name}</div>
          {s.topics.length > 0 && <div className="max-w-72 truncate text-xs text-muted-foreground">{s.topics.map((x) => `${x.title} (${x.n})`).join(" · ")}</div>}
          <div className="max-w-72 truncate text-[11px] text-muted-foreground">{s.groups.join(", ")}</div>
        </div>
      </div>
    ) },
    { key: "answers", header: t("anAnswers"), align: "right", sort: (s) => s.answers, cell: (s) => (
      <span className="font-mono">{s.answers}{s.panel > 0 && <span className="text-xs text-muted-foreground"> ({s.panel} panel)</span>}</span>
    ) },
    { key: "share", header: t("anShare"), align: "right", sort: (s) => s.share, cell: (s) => (
      <div><div className="font-mono text-xs">{s.share}%</div>
        <div className="ml-auto mt-1 h-1 w-16 rounded-full bg-muted"><div className="h-1 rounded-full bg-primary" style={{ width: `${s.share}%` }} /></div></div>
    ) },
    { key: "res", header: t("colResolved"), align: "right", sort: (s) => s.resolved ?? 0, cell: (s) => (
      <span className="font-mono"><span className="text-success">{s.resolved ?? 0}</span>
        {(s.unresolved ?? 0) > 0 && <span className="text-destructive"> / {s.unresolved}</span>}</span>
    ) },
    { key: "react", header: t("anReacts"), align: "right", sort: (s) => s.reactions ?? 0, cell: (s) => (
      <span className="font-mono">{s.reactions ?? 0}{(s.working ?? 0) > 0 && <span className="block text-[11px] text-primary">{t("anWorking")}: {s.working}</span>}</span>
    ) },
    { key: "clar", header: t("anClar"), align: "right", sort: (s) => s.clarifications, cell: (s) => <span className="font-mono">{s.clarifications}</span> },
    { key: "speed", header: t("anSpeed"), align: "right", sort: (s) => s.median_s, cell: (s) => (
      <span className="font-mono text-xs">{fmtDur(t, s.median_s)}
        {s.avg_s != null && <span className="block text-muted-foreground">⌀ {fmtDur(t, s.avg_s)}</span>}</span>
    ) },
    { key: "day", header: t("anPerDay"), align: "right", sort: (s) => s.per_day, cell: (s) => (
      <span className="font-mono">{s.per_day}<span className="block text-[11px] text-muted-foreground">{t("anDays", { n: s.active_days })}</span></span>
    ) },
    { key: "msgs", header: t("anMessages"), align: "right", sort: (s) => s.messages, cell: (s) => <span className="font-mono">{s.messages}</span> },
    { key: "appr", header: t("anApproved"), align: "right", sort: (s) => s.approved, cell: (s) => <span className="font-mono">{s.approved}/{s.candidates}</span> },
  ];
  return (
    <Panel title={t("anStaff")} icon={UserRound}>
      <DataTable rows={a.staff} columns={columns} rowKey={(s) => s.name} t={t} initialSort={{ key: "answers", dir: "desc" }}
        search={(s) => [s.name, ...s.groups, ...s.topics.map((x) => x.title)].join(" ")}
        filters={[{ value: "all", label: t("dtAll"), test: () => true },
          { value: "active", label: t("anAnswers"), test: (s) => s.answers > 0 }]} />
    </Panel>
  );
}

function Askers({ a, t }: { a: Analytics; t: ST }) {
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
      <Panel title={t("anAskers")} hint={t("anAskersHint")} icon={Users}>
        <DataTable rows={a.askers} columns={askerCols(t)} rowKey={(u) => u.user} t={t} initialSort={{ key: "q", dir: "desc" }}
          search={(u) => [u.name, u.username, u.staff_person, ...u.top_types.map((x) => x.title)].join(" ")} />
      </Panel>
      <Panel title={t("anAsks")} hint={t("anAsksHint")} icon={MessageCircleQuestion}>
        {a.top_asks.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
        <div className="grid gap-2">
          {a.top_asks.map((x, i) => (
            <div key={i} className="flex items-start gap-2 text-sm">
              <Badge variant="outline" className="shrink-0 font-mono">{x.count}</Badge><span className="leading-snug">{x.text}</span>
            </div>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function Topics({ a, t }: { a: Analytics; t: ST }) {
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Panel title={t("anTopTypes")} hint={t("anTopTypesHint")} icon={Tags}>
        <Bars rows={a.top_types.map((x) => ({ key: String(x.entry), label: x.title, n: x.n }))} empty={t("empty")} />
      </Panel>
      <Panel title={t("anZones")} icon={Target}>
        <Bars rows={Object.entries(a.zones).sort((x, y) => y[1] - x[1]).map(([z, n]) => ({ key: z, label: z, n }))} empty={t("empty")} />
      </Panel>
    </div>
  );
}

function askerCols(t: ST): Column<Analytics["askers"][number]>[] {
  return [
    { key: "name", header: t("anAsker"), sort: (u) => (u.name || "").toLowerCase(), cell: (u) => (
      <div className="flex min-w-52 items-center gap-2.5">
        <Initials name={u.name} className="size-8" />
        <div className="min-w-0">
          <div className="font-medium">{u.name || "—"}{u.username && <span className="font-normal text-muted-foreground"> @{u.username}</span>}</div>
          {u.staff_person && <div className="text-xs text-muted-foreground">{u.staff_person}</div>}
          {u.top_types.length > 0 && <div className="max-w-md truncate text-xs text-muted-foreground">{u.top_types.map((x) => `${x.title} (${x.n})`).join(" · ")}</div>}
        </div>
      </div>
    ) },
    { key: "q", header: t("anQuestions"), align: "right", sort: (u) => u.questions, cell: (u) => <span className="font-mono">{u.questions}</span> },
    { key: "bot", header: t("kpiBot"), align: "right", sort: (u) => u.bot, cell: (u) => <span className="font-mono text-success">{u.bot}</span> },
    { key: "esc", header: t("kpiHuman"), align: "right", sort: (u) => u.escalated, cell: (u) => <span className="font-mono text-warning">{u.escalated}</span> },
  ];
}
