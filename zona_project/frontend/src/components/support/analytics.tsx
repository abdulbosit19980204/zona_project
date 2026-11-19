"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, HelpCircle, Image as ImageIcon, Inbox, ListChecks, UserRound } from "lucide-react";
import { SupportShell } from "./shell";
import { useState } from "react";

import { SectionTitle, StatCard } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";

import { supportApi } from "./api";
import { stageLabel } from "./common";
import { useSt, type SKey } from "./i18n";

/** Tahlil: savollar, bot ishi, xodimlar javoblari va javobdan oldin so'raladigan ma'lumotlar. */
export function SupportAnalytics() {
  const t = useSt();
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ["support", "analytics", days], queryFn: () => supportApi.analytics(days), refetchInterval: 60_000 });
  const a = q.data;
  const botClosed = a ? ["template", "faq", "rule", "ai"].reduce((s, k) => s + (a.by_stage[k] ?? 0), 0) : 0;
  const maxDay = Math.max(1, ...(a?.daily ?? []).map((d) => d.total));
  const maxGroup = Math.max(1, ...(a?.groups ?? []).map((g) => g.n));

  return (
    <SupportShell title={t("anTitle")} description={t("anDesc")}
        actions={(
          <Tabs value={String(days)} onValueChange={(v) => setDays(Number(v))}>
            <TabsList>
              <TabsTrigger value="7">{t("days7")}</TabsTrigger>
              <TabsTrigger value="30">{t("days30")}</TabsTrigger>
              <TabsTrigger value="90">{t("days90")}</TabsTrigger>
            </TabsList>
          </Tabs>
        )}>
      {!a && <Skeleton className="h-96" />}
      {a && (
        <div className="grid gap-6">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            <StatCard label={t("anQuestions")} value={a.questions} icon={Inbox} />
            <StatCard label={t("kpiBot")} value={botClosed} icon={Bot} tone="success" />
            <StatCard label={t("anUnanswered")} value={a.unanswered} icon={HelpCircle} tone="warning" />
            <StatCard label={t("anPhoto")} value={a.with_photo} icon={ImageIcon} />
            <StatCard label={t("anAskFirst")} value={a.entries_with_ask_first} icon={ListChecks} />
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            {Object.entries(a.by_source).map(([k, v]) => (
              <Badge key={k} variant="outline" className="font-normal">{t("anSource")}: {t(`src_${k}` as SKey)} · {v}</Badge>
            ))}
            {Object.entries(a.by_stage).map(([k, v]) => (
              <Badge key={k} variant="outline" className="font-normal">{stageLabel(k, t) || k} · {v}</Badge>
            ))}
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <section>
              <SectionTitle>{t("anPt")}</SectionTitle>
              <Card className="gap-2 p-3 text-sm">
                <div className="flex flex-wrap gap-3">
                  <span>{t("anQuestions")}: <b>{a.protarget.questions}</b></span>
                  <span>{t("kpiBot")}: <b>{a.protarget.by_bot}</b></span>
                  <span>{t("anUnanswered")}: <b>{a.protarget.unanswered}</b></span>
                  <span>{t("anPtTeam")}: <b>{a.protarget.team_answers}</b>
                    {a.protarget.team_median_minutes != null && ` · ${t("anMin", { n: a.protarget.team_median_minutes })}`}</span>
                </div>
                {a.protarget.types.map((x) => (
                  <div key={x.title} className="flex justify-between gap-2 text-xs"><span className="truncate">{x.title}</span><span className="font-mono">{x.n}</span></div>
                ))}
              </Card>
            </section>
            <section>
              <SectionTitle>{t("anImages")}</SectionTitle>
              <Card className="gap-2 p-3 text-sm">
                <div className="flex flex-wrap gap-3">
                  <span>{t("anImgTotal")}: <b>{a.images.total}</b></span>
                  <span>{t("anImgLabeled")}: <b>{a.images.labeled}</b></span>
                  <span>{t("anImgTypes")}: <b>{a.images.types}</b></span>
                  <span>{t("anImgByImage")}: <b>{a.images.by_image}</b></span>
                </div>
                {Object.entries(a.zones).sort((x, y) => y[1] - x[1]).map(([z, n]) => (
                  <div key={z} className="flex justify-between gap-2 text-xs"><span className="truncate">{z}</span><span className="font-mono">{n}</span></div>
                ))}
              </Card>
            </section>
          </div>

          <section>
            <SectionTitle><span className="inline-flex items-center gap-1.5"><UserRound className="size-4" />{t("anStaff")}</span></SectionTitle>
            <Card className="p-0">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>{t("staff")}</TableHead>
                    <TableHead className="text-right">{t("anAnswers")}</TableHead>
                    <TableHead className="text-right">{t("anClar")}</TableHead>
                    <TableHead className="text-right">{t("anSpeed")}</TableHead>
                    <TableHead className="text-right">{t("anCand")}</TableHead>
                    <TableHead className="text-right">{t("anApproved")}</TableHead>
                    <TableHead>{t("groups")}</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {a.staff.length === 0 && <TableRow><TableCell colSpan={7} className="text-muted-foreground">{t("empty")}</TableCell></TableRow>}
                  {a.staff.map((s) => (
                    <TableRow key={s.name}>
                      <TableCell className="font-medium">{s.name}</TableCell>
                      <TableCell className="text-right font-mono">{s.answers}{s.panel > 0 && <span className="text-xs text-muted-foreground"> ({s.panel} panel)</span>}</TableCell>
                      <TableCell className="text-right font-mono">{s.clarifications}</TableCell>
                      <TableCell className="text-right font-mono">{s.median_minutes == null ? "—" : t("anMin", { n: s.median_minutes })}</TableCell>
                      <TableCell className="text-right font-mono">{s.candidates}</TableCell>
                      <TableCell className="text-right font-mono">{s.approved}</TableCell>
                      <TableCell className="max-w-56 truncate text-xs text-muted-foreground">{s.groups.join(", ")}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Card>
          </section>

          <div className="grid gap-6 lg:grid-cols-2">
            <section>
              <SectionTitle>{t("anAsks")}</SectionTitle>
              <p className="mb-2 text-xs text-muted-foreground">{t("anAsksHint")}</p>
              <Card className="gap-1.5 p-3">
                {a.top_asks.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
                {a.top_asks.map((x, i) => (
                  <div key={i} className="flex items-start gap-2 text-sm">
                    <Badge variant="outline" className="shrink-0 font-mono">{x.count}</Badge><span>{x.text}</span>
                  </div>
                ))}
              </Card>
            </section>
            <section>
              <SectionTitle>{t("anGroups")}</SectionTitle>
              <Card className="gap-2 p-3">
                {a.groups.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
                {a.groups.map((g) => (
                  <div key={g.title} className="grid gap-1 text-sm">
                    <div className="flex justify-between"><span className="truncate">{g.title}</span><span className="font-mono">{g.n}</span></div>
                    <div className="h-1.5 rounded-full bg-muted"><div className="h-1.5 rounded-full bg-primary" style={{ width: `${(100 * g.n) / maxGroup}%` }} /></div>
                  </div>
                ))}
              </Card>
            </section>
          </div>

          <section>
            <SectionTitle>{t("anDaily")}</SectionTitle>
            <Card className="p-3">
              {a.daily.length === 0 && <p className="text-sm text-muted-foreground">{t("empty")}</p>}
              <div className="flex h-40 items-end gap-1 overflow-x-auto">
                {a.daily.map((d) => (
                  <div key={d.date} className="flex min-w-3 flex-1 flex-col justify-end" title={`${d.date}: ${d.total} (bot ${d.bot}, ${d.staff})`}>
                    <div className="rounded-t bg-primary/30" style={{ height: `${(100 * (d.total - d.bot - d.staff)) / maxDay}%` }} />
                    <div className="bg-success/70" style={{ height: `${(100 * d.staff) / maxDay}%` }} />
                    <div className="bg-primary" style={{ height: `${(100 * d.bot) / maxDay}%` }} />
                  </div>
                ))}
              </div>
              <div className="mt-2 flex flex-wrap gap-3 text-xs text-muted-foreground">
                <span className="inline-flex items-center gap-1"><span className="size-2 rounded bg-primary" />{t("kpiBot")}</span>
                <span className="inline-flex items-center gap-1"><span className="size-2 rounded bg-success/70" />{t("staffAnswers")}</span>
                <span className="inline-flex items-center gap-1"><span className="size-2 rounded bg-primary/30" />{t("anUnanswered")}</span>
              </div>
            </Card>
          </section>
        </div>
      )}
    </SupportShell>
  );
}
