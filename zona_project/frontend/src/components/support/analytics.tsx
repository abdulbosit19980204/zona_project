"use client";

import { useQuery } from "@tanstack/react-query";
import { BarChart3, Bot, Clock3, Zap, HelpCircle, Image as ImageIcon, Inbox, ListChecks, MessageCircleQuestion, Tags, Target, UserRound, Users } from "lucide-react";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

import { supportApi, type Analytics } from "./api";
import { Initials, Metric, Panel, Segmented, stageLabel } from "./common";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";
import { Speed } from "./speed";
import { Workload } from "./workload";

type Tab = "overview" | "speed" | "workload" | "staff" | "askers" | "topics";

/** Tahlil: savollar, bot ishi, xodimlar javoblari va javobdan oldin so'raladigan ma'lumotlar — bo'limlarga ajratilgan. */
export function SupportAnalytics() {
  const t = useSt();
  const [days, setDays] = useState("30");
  const [tab, setTab] = useState<Tab>("overview");
  const q = useQuery({ queryKey: ["support", "analytics", days], queryFn: () => supportApi.analytics(Number(days)), refetchInterval: 60_000 });
  const a = q.data;
  const botClosed = a ? ["template", "faq", "rule", "ai", "image"].reduce((s, k) => s + (a.by_stage[k] ?? 0), 0) : 0;

  return (
    <SupportShell title={t("anTitle")} description={t("anDesc")}
      actions={<Segmented size="sm" value={days} onChange={setDays} options={[
        { value: "7", label: t("days7") }, { value: "30", label: t("days30") }, { value: "90", label: t("days90") },
      ]} />}>
      {!a && <div className="grid gap-4"><Skeleton className="h-20" /><Skeleton className="h-96" /></div>}
      {a && (
        <div className="grid gap-5">
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
            <Metric label={t("anQuestions")} value={a.questions} icon={Inbox} tone="primary" />
            <Metric label={t("kpiBot")} value={botClosed} hint={a.questions ? `${Math.round((100 * botClosed) / a.questions)}%` : undefined} icon={Bot} tone="success" />
            <Metric label={t("anUnanswered")} value={a.unanswered} icon={HelpCircle} tone="warning" />
            <Metric label={t("anPhoto")} value={a.with_photo} icon={ImageIcon} />
            <Metric label={t("anAskFirst")} value={a.entries_with_ask_first} icon={ListChecks} />
          </div>

          <Segmented value={tab} onChange={setTab} options={[
            { value: "overview", label: t("anTabOverview"), icon: BarChart3 },
            { value: "speed", label: t("anTabSpeed"), icon: Zap },
            { value: "workload", label: t("anTabWorkload"), icon: Clock3 },
            { value: "staff", label: t("anTabStaff"), icon: UserRound, count: a.staff.length },
            { value: "askers", label: t("anTabAskers"), icon: Users, count: a.askers.length },
            { value: "topics", label: t("anTabTopics"), icon: Tags },
          ]} />

          {tab === "overview" && <Overview a={a} t={t} />}
          {tab === "speed" && <Speed days={Number(days)} t={t} />}
          {tab === "workload" && <Workload days={Number(days)} t={t} />}
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

function Overview({ a, t }: { a: Analytics; t: ST }) {
  const maxDay = Math.max(1, ...a.daily.map((d) => d.total));
  return (
    <div className="grid gap-4">
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
            <Stat label={t("anPtTeam")} value={<>{a.protarget.team_answers}{a.protarget.team_median_minutes != null && <span className="text-xs font-normal text-muted-foreground"> · {t("anMin", { n: a.protarget.team_median_minutes })}</span>}</>} />
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
          {Object.entries(a.by_source).map(([k, v]) => (
            <Badge key={k} variant="secondary" className="gap-1.5 font-normal">{t("anSource")}: {t(`src_${k}` as SKey)}<span className="font-mono font-semibold">{v}</span></Badge>
          ))}
        </div>
      </Panel>
    </div>
  );
}

function StaffTable({ a, t }: { a: Analytics; t: ST }) {
  return (
    <Panel title={t("anStaff")} icon={UserRound} bodyClassName="p-0">
      <Table>
        <TableHeader>
          <TableRow className="bg-muted/40">
            <TableHead className="pl-4">{t("staff")}</TableHead>
            <TableHead className="text-right">{t("anAnswers")}</TableHead>
            <TableHead className="text-right">{t("anShare")}</TableHead>
            <TableHead className="text-right">{t("anClar")}</TableHead>
            <TableHead className="text-right">{t("anSpeed")}</TableHead>
            <TableHead className="text-right">{t("anPerDay")}</TableHead>
            <TableHead className="text-right">{t("anMessages")}</TableHead>
            <TableHead className="pr-4 text-right">{t("anApproved")}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {a.staff.length === 0 && <TableRow><TableCell colSpan={8} className="pl-4 text-muted-foreground">{t("empty")}</TableCell></TableRow>}
          {a.staff.map((s) => (
            <TableRow key={s.name}>
              <TableCell className="pl-4">
                <div className="flex items-center gap-2.5">
                  <Initials name={s.name} className="size-8" />
                  <div className="min-w-0">
                    <div className="font-medium">{s.name}</div>
                    {s.topics.length > 0 && <div className="max-w-72 truncate text-xs text-muted-foreground">{s.topics.map((x) => `${x.title} (${x.n})`).join(" · ")}</div>}
                    <div className="max-w-72 truncate text-[11px] text-muted-foreground">{s.groups.join(", ")}</div>
                  </div>
                </div>
              </TableCell>
              <TableCell className="text-right font-mono">{s.answers}{s.panel > 0 && <span className="text-xs text-muted-foreground"> ({s.panel} panel)</span>}</TableCell>
              <TableCell className="text-right">
                <div className="font-mono text-xs">{s.share}%</div>
                <div className="ml-auto mt-1 h-1 w-16 rounded-full bg-muted"><div className="h-1 rounded-full bg-primary" style={{ width: `${s.share}%` }} /></div>
              </TableCell>
              <TableCell className="text-right font-mono">{s.clarifications}</TableCell>
              <TableCell className="text-right font-mono text-xs">{s.median_minutes == null ? "—" : t("anMin", { n: s.median_minutes })}
                {s.avg_minutes != null && <div className="text-muted-foreground">⌀ {t("anMin", { n: s.avg_minutes })}</div>}</TableCell>
              <TableCell className="text-right font-mono">{s.per_day}<div className="text-[11px] text-muted-foreground">{t("anDays", { n: s.active_days })}</div></TableCell>
              <TableCell className="text-right font-mono">{s.messages}</TableCell>
              <TableCell className="pr-4 text-right font-mono">{s.approved}/{s.candidates}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </Panel>
  );
}

function Askers({ a, t }: { a: Analytics; t: ST }) {
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
      <Panel title={t("anAskers")} hint={t("anAskersHint")} icon={Users} bodyClassName="p-0">
        <Table>
          <TableHeader>
            <TableRow className="bg-muted/40"><TableHead className="pl-4">{t("anAsker")}</TableHead><TableHead className="text-right">{t("anQuestions")}</TableHead>
              <TableHead className="text-right">{t("kpiBot")}</TableHead><TableHead className="pr-4 text-right">{t("kpiHuman")}</TableHead></TableRow>
          </TableHeader>
          <TableBody>
            {a.askers.length === 0 && <TableRow><TableCell colSpan={4} className="pl-4 text-muted-foreground">{t("empty")}</TableCell></TableRow>}
            {a.askers.slice(0, 50).map((u) => (
              <TableRow key={u.user}>
                <TableCell className="pl-4">
                  <div className="flex items-center gap-2.5">
                    <Initials name={u.name} className="size-8" />
                    <div className="min-w-0">
                      <div className="font-medium">{u.name || "—"}{u.username && <span className="font-normal text-muted-foreground"> @{u.username}</span>}</div>
                      {u.staff_person && <div className="text-xs text-muted-foreground">{u.staff_person}</div>}
                      {u.top_types.length > 0 && <div className="max-w-md truncate text-xs text-muted-foreground">{u.top_types.map((x) => `${x.title} (${x.n})`).join(" · ")}</div>}
                    </div>
                  </div>
                </TableCell>
                <TableCell className="text-right font-mono">{u.questions}</TableCell>
                <TableCell className="text-right font-mono text-success">{u.bot}</TableCell>
                <TableCell className="pr-4 text-right font-mono text-warning">{u.escalated}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
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
