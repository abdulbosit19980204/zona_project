"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  AlarmClock, CheckCheck, CheckCircle2, CircleAlert, CircleDot, ExternalLink, Flame, ListTodo, MessageSquareText, Play,
  Search, Timer, TrendingUp, XCircle,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";

import { EmptyState, StatCard } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { api, errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

export interface CTask {
  id: number; code: string; title: string; status: string; category: string; assignee: string; due_at: string | null;
  due_in: number | null; url: string; created_at: string | null; completed_at: string | null; completed_by: string;
  asker: string; group: string; q_text: string; q_link: string; q_resolution: string; pushed: string; status_error: string;
  on_time: boolean | null; question: number | null;
}
interface Pending { id: number; text: string; asker: string; group: string; created_at: string; status: string; link: string }
interface Summary {
  open: number; overdue: number; due_soon: number; in_progress: number; done_today: number; done_week: number;
  on_time_pct: number | null; median_minutes: number | null; untasked: number; sla_minutes: number;
}
interface ControlData { summary: Summary; open: CTask[]; done: CTask[]; untasked: Pending[]; worker_alive: boolean }

type Filter = "all" | "overdue" | "new" | "in_progress";

/** Soniya -> "4:05" yoki "1 soat 12 daq". */
function clock(sec: number) {
  const s = Math.abs(sec);
  if (s >= 3600) return `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")} h`;
  return `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, "0")}`;
}

function useNow(ms = 1000) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), ms);
    return () => clearInterval(id);
  }, [ms]);
  return now;
}

const tone = (left: number | null) =>
  left == null ? "none" : left < 0 ? "late" : left < 180 ? "soon" : "ok";
const BAR = { late: "bg-destructive", soon: "bg-warning", ok: "bg-success", none: "bg-muted-foreground/30" } as const;
const CHIP = {
  late: "bg-destructive/12 text-destructive", soon: "bg-warning/15 text-warning", ok: "bg-success/12 text-success",
  none: "bg-muted text-muted-foreground",
} as const;

export function PrbcControl() {
  const t = useTranslations("prbc");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["prbc", "control"], queryFn: async () => (await api.get<ControlData>("prbc/control/")).data,
    refetchInterval: 15_000 });
  const fetchedAt = q.dataUpdatedAt;
  const now = useNow();
  const [filter, setFilter] = useState<Filter>("all");
  const [search, setSearch] = useState("");
  const [who, setWho] = useState("");
  const [showPending, setShowPending] = useState(false);

  const setStatus = useMutation({
    mutationFn: (v: { id: number; category: string }) => api.post(`prbc/tasks/${v.id}/status/`, { category: v.category }),
    onSuccess: (_r, v) => { toast.success(t(v.category === "done" ? "ctlDoneOk" : "ctlProgressOk")); qc.invalidateQueries({ queryKey: ["prbc"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const backfill = useMutation({
    mutationFn: async () => (await api.post<{ count: number }>("prbc/tasks/backfill/", {})).data,
    onSuccess: (r) => { toast.success(t("ctlBackfillOk", { n: r.count })); qc.invalidateQueries({ queryKey: ["prbc"] }); },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const data = q.data;
  const left = (x: CTask) => (x.due_in == null ? null : x.due_in - (now - fetchedAt) / 1000);
  const assignees = useMemo(() => Array.from(new Set((data?.open ?? []).map((x) => x.assignee).filter(Boolean))).sort(), [data]);
  const rows = (data?.open ?? []).filter((x) => {
    if (filter === "overdue" && !((left(x) ?? 1) < 0)) return false;
    if (filter === "new" && x.category !== "new") return false;
    if (filter === "in_progress" && x.category !== "in_progress") return false;
    if (who && x.assignee !== who) return false;
    const s = search.trim().toLowerCase();
    return !s || `${x.code} ${x.title} ${x.asker} ${x.group} ${x.assignee}`.toLowerCase().includes(s);
  });

  if (q.isPending) return <Skeleton className="h-96 rounded-xl" />;
  if (!data) return <EmptyState icon={CircleAlert} title={t("ctlError")} />;
  const s = data.summary;
  const counts: Record<Filter, number> = {
    all: data.open.length, overdue: data.open.filter((x) => (left(x) ?? 1) < 0).length,
    new: data.open.filter((x) => x.category === "new").length, in_progress: data.open.filter((x) => x.category === "in_progress").length,
  };

  return (
    <div className="grid gap-4">
      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label={t("ctlOpen")} value={s.open} icon={ListTodo} hint={t("ctlInProgress", { n: s.in_progress })} />
        <StatCard label={t("ctlOverdue")} value={s.overdue} icon={Flame} tone={s.overdue ? "danger" : "default"} />
        <StatCard label={t("ctlDueSoon")} value={s.due_soon} icon={AlarmClock} tone={s.due_soon ? "warning" : "default"} />
        <StatCard label={t("ctlDoneToday")} value={s.done_today} icon={CheckCheck} tone="success" hint={t("ctlWeek", { n: s.done_week })} />
        <StatCard label={t("ctlOnTime")} value={s.on_time_pct == null ? "—" : `${s.on_time_pct}%`} icon={TrendingUp}
          tone={s.on_time_pct == null ? "default" : s.on_time_pct >= 80 ? "success" : s.on_time_pct >= 50 ? "warning" : "danger"}
          hint={t("ctlNorm", { n: s.sla_minutes })} />
        <StatCard label={t("ctlMedian")} value={s.median_minutes == null ? "—" : t("ctlMin", { n: s.median_minutes })} icon={Timer}
          tone={s.median_minutes != null && s.median_minutes <= s.sla_minutes ? "success" : "default"} hint={t("ctl7days")} />
      </div>

      {s.untasked > 0 && (
        <Card className="gap-3 border-warning/40 bg-warning/5 p-4">
          <div className="flex flex-wrap items-center gap-3">
            <CircleAlert className="size-5 shrink-0 text-warning" />
            <div className="min-w-0 flex-1">
              <div className="font-medium">{t("ctlUntasked", { n: s.untasked })}</div>
              <div className="text-xs text-muted-foreground">{t("ctlUntaskedHint")}</div>
            </div>
            <Button size="sm" variant="ghost" onClick={() => setShowPending(!showPending)}>{t(showPending ? "ctlHide" : "ctlShow")}</Button>
            <Button size="sm" disabled={backfill.isPending}
              onClick={() => { if (confirm(t("ctlBackfillConfirm", { n: s.untasked }))) backfill.mutate(); }}>
              <ListTodo className="size-4" />{t("ctlBackfill")}
            </Button>
          </div>
          {showPending && (
            <div className="divide-y rounded-lg border bg-card text-sm">
              {data.untasked.map((p) => (
                <div key={p.id} className="flex flex-wrap items-center gap-x-3 gap-y-0.5 px-3 py-2">
                  <span className="min-w-0 flex-1 truncate">{p.text || "—"}</span>
                  <span className="text-xs text-muted-foreground">{p.asker}{p.group && ` · ${p.group}`} · {format(new Date(p.created_at), "dd.MM HH:mm")}</span>
                  {p.link && <a href={p.link} target="_blank" rel="noreferrer" className="text-primary"><MessageSquareText className="size-4" /></a>}
                </div>
              ))}
            </div>
          )}
        </Card>
      )}

      <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
        <Card className="gap-0 overflow-hidden p-0">
          <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
            <div className="mr-auto">
              <div className="font-semibold">{t("ctlBoard")}</div>
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                {data.worker_alive ? <CheckCircle2 className="size-3.5 text-success" /> : <XCircle className="size-3.5 text-destructive" />}
                {t(data.worker_alive ? "ctlLive" : "workerDown")}
              </div>
            </div>
            {(["all", "overdue", "new", "in_progress"] as Filter[]).map((k) => (
              <button key={k} type="button" onClick={() => setFilter(k)}
                className={cn("h-8 rounded-full border px-3 text-xs font-medium transition-colors",
                  filter === k ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground",
                  k === "overdue" && counts.overdue > 0 && filter !== k && "border-destructive/40 text-destructive")}>
                {t(`ctlF_${k}`)} · {counts[k]}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2 border-b bg-muted/30 px-4 py-2">
            <div className="relative min-w-48 flex-1">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input className="h-9 pl-8" value={search} onChange={(e) => setSearch(e.target.value)} placeholder={t("ctlSearch")} />
            </div>
            <select className="h-9 rounded-md border bg-card px-2 text-sm" value={who} onChange={(e) => setWho(e.target.value)}>
              <option value="">{t("ctlAllAssignees")}</option>
              {assignees.map((a) => <option key={a} value={a}>{a}</option>)}
            </select>
          </div>
          {!rows.length ? (
            <div className="p-6"><EmptyState icon={CheckCircle2} title={t(data.open.length ? "ctlNoMatch" : "ctlAllClear")} /></div>
          ) : (
            <div className="divide-y">
              {rows.map((x) => {
                const l = left(x);
                const tn = tone(l);
                return (
                  <div key={x.id} className="relative flex flex-wrap items-center gap-x-3 gap-y-1.5 py-3 pl-5 pr-4">
                    <span className={cn("absolute inset-y-0 left-0 w-1", BAR[tn])} />
                    <span className={cn("inline-flex h-7 min-w-[74px] items-center justify-center gap-1 rounded-md px-2 font-mono text-xs font-semibold tabular-nums", CHIP[tn])}
                      title={x.due_at ? `${t("tDue")}: ${format(new Date(x.due_at), "dd.MM HH:mm")}` : t("ctlNoDue")}>
                      {l == null ? "—" : l < 0 ? `+${clock(l)}` : clock(l)}
                    </span>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-mono text-[11px] text-muted-foreground">{x.code}</span>
                        <span className="truncate text-sm font-medium">{x.title}</span>
                      </div>
                      <div className="truncate text-xs text-muted-foreground">
                        {x.asker && <>🙋 {x.asker}</>}{x.group && <> · {x.group}</>}<> · 👤 {x.assignee || "—"}</>
                        {x.status_error && <span className="text-destructive"> · ⚠ {x.status_error}</span>}
                      </div>
                    </div>
                    <Badge variant="outline" className={cn("gap-1", x.category === "in_progress" && "border-primary/40 text-primary")}>
                      <CircleDot className="size-3" />{x.status || "—"}
                    </Badge>
                    <div className="flex items-center gap-1">
                      {x.category === "new" && (
                        <Button size="sm" variant="outline" className="h-8" disabled={setStatus.isPending}
                          onClick={() => setStatus.mutate({ id: x.id, category: "in_progress" })} title={t("ctlStart")}>
                          <Play className="size-3.5" /><span className="hidden sm:inline">{t("ctlStart")}</span>
                        </Button>
                      )}
                      <Button size="sm" className="h-8" disabled={setStatus.isPending}
                        onClick={() => { if (confirm(t("ctlDoneConfirm", { code: x.code }))) setStatus.mutate({ id: x.id, category: "done" }); }}>
                        <CheckCheck className="size-3.5" /><span className="hidden sm:inline">{t("ctlDone")}</span>
                      </Button>
                      {x.q_link && (
                        <Button size="icon" variant="ghost" className="size-8" asChild title={t("ctlOpenQuestion")}>
                          <a href={x.q_link} target="_blank" rel="noreferrer"><MessageSquareText className="size-4" /></a>
                        </Button>
                      )}
                      <Button size="icon" variant="ghost" className="size-8" asChild title={t("openInPrbc")}>
                        <a href={x.url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" /></a>
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </Card>

        <Card className="h-fit gap-0 overflow-hidden p-0">
          <div className="border-b px-4 py-3">
            <div className="font-semibold">{t("ctlDoneList")}</div>
            <div className="text-xs text-muted-foreground">{t("ctlDoneListHint")}</div>
          </div>
          {!data.done.length ? <div className="px-4 py-6 text-sm text-muted-foreground">{t("ctlNoneDone")}</div> : (
            <div className="max-h-[560px] divide-y overflow-y-auto">
              {data.done.map((x) => {
                const mins = x.completed_at && x.created_at ? Math.round((+new Date(x.completed_at) - +new Date(x.created_at)) / 60000) : null;
                const late = mins != null && mins > s.sla_minutes;
                return (
                  <a key={x.id} href={x.url} target="_blank" rel="noreferrer" className="block px-4 py-2.5 hover:bg-muted/50">
                    <div className="flex items-center gap-2">
                      <CheckCircle2 className="size-3.5 shrink-0 text-success" />
                      <span className="truncate text-sm">{x.title}</span>
                    </div>
                    <div className="mt-0.5 flex flex-wrap gap-x-2 pl-5 text-xs text-muted-foreground">
                      <span>{x.completed_by || x.assignee || "—"}</span>
                      {x.completed_at && <span>· {format(new Date(x.completed_at), "dd.MM HH:mm")}</span>}
                      {mins != null && <span className={late ? "text-warning" : "text-success"}>· {t("ctlMin", { n: mins })}</span>}
                      {x.pushed === "done" && <span title={t("ctlAutoClosedHint")}>· {t("ctlAutoClosed")}</span>}
                    </div>
                  </a>
                );
              })}
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
