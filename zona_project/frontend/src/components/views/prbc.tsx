"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { format } from "date-fns";
import {
  CheckCircle2, CircleAlert, ExternalLink, Link2, ListTodo, Plug, RefreshCcwDot, RotateCcw, Search, Timer, UserMinus, Users,
} from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";
import { toast } from "sonner";

import { EmptyState, Page, PageHeader, StatCard } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Textarea } from "@/components/ui/textarea";
import { api, errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import { PrbcControl } from "./prbc-control";

type Status = "active" | "leaving" | "left";
type LinkField = "staff_person" | "member" | "inv_employee" | "tg_user";
interface Ref { id: number; label: string }
interface Conn {
  enabled: boolean; base_url: string; phone: string; lifecycle_project: number | null; task_project: number | null;
  task_default_assignees: number[]; sync_minutes: number; auto_left: boolean; comment_devices: boolean; password_set: boolean;
  me: { full_name?: string; position?: string }; last_sync_at: string | null; last_error: string; sync_requested: boolean;
  worker_alive: boolean; task_watchers: number[]; close_on_done: boolean; named: Record<string, string>;
  notify_done: boolean; notify_created: boolean; attach_files: boolean; assignee_map: Record<string, number>;
  watch_self: boolean; outlet_lookup: boolean; ready: boolean; not_ready: string;
  sla_minutes: number; task_priority: number; work_start: number; work_end: number; work_days: number[];
  sync_status: boolean; overdue_alert: boolean; task_all_escalated: boolean;
}
interface Person {
  id: number; prbc_user: number | null; tab_number: string; full_name: string; position: string; department: string; company: string;
  phone: string; status: Status; hired_on: string | null; left_on: string | null; left_reason: string; leave_task: string;
  link_manual: boolean; left_applied: boolean; links: Record<LinkField, Ref | null>; agent_code: string; code_manual: boolean;
}
interface Overview {
  connection: Conn; people: { total: number; active?: number; leaving?: number; left?: number };
  linked: { unlinked: number }; month: { left: number; new: number };
  left_members: { person: string; member: string; left_on: string | null }[];
  runs: { id: number; started_at: string; ok: boolean; stats: Record<string, unknown>; error: string }[];
}
interface TPerson { id: number; name: string; position: string; role: "assignee" | "co_assignee" | "observer" }
interface PTask {
  id: number; code: string; title: string; kind: string; status: string; category: string; project: string; assignee: string;
  due_at: string | null; person_name: string; url: string; created_by: string; created_at: string | null; people: TPerson[];
  watchers: string; completed_at: string | null; completed_by: string; spent_minutes: number | null; overdue: boolean;
  on_time: boolean | null; has_report: boolean; question: number | null; files: number; notified: string[];
  report?: {
    completed_by?: string; spent_minutes?: number | null; on_time?: boolean | null;
    comments?: { at: string | null; by: string; text: string }[];
    checklist?: { title: string; done: number; total: number; items: { text: string; done: boolean }[] }[];
    worklog?: { entries?: { by: string; minutes: number | null; note: string }[] };
    history?: { at: string | null; verb: string; by: string; meta: Record<string, unknown> }[];
  };
}
interface StatRow { name: string; total: number; done: number; open: number; overdue: number; late: number; cancelled: number; avg_hours: number | null }
interface GroupRow { name: string; total: number; done: number; open: number; overdue: number; cancelled: number }
interface TestResult { ok: boolean; me: { full_name?: string }; checks: Record<string, { ok: boolean; count?: number; detail?: string }>; projects: { id: number; name: string }[] }

interface Project { id: number; name: string; open?: number | null }
interface GroupProject {
  id: number; title: string; questions: number; project: number | null; project_name: string; suggested: number | null; suggested_name: string;
  creates_tasks: boolean; old: boolean; redirect_title: string; owner: number | null; owner_name: string; auto_owner: number | null; auto_owner_name: string;
}

const get = async <T,>(url: string, params?: Record<string, string | number>) => (await api.get<T>(url, { params })).data;
const d = (v: string | null | undefined, time = false) => (v ? format(new Date(v), time ? "dd.MM.yyyy HH:mm" : "dd.MM.yyyy") : "—");
const STATUS_TONE: Record<Status, string> = { active: "bg-success/15 text-success", leaving: "bg-warning/15 text-warning", left: "bg-destructive/15 text-destructive" };
const LINKS: LinkField[] = ["staff_person", "member", "inv_employee", "tg_user"];
const LINK_KEY: Record<LinkField, string> = { staff_person: "lStaff", member: "lMember", inv_employee: "lInv", tg_user: "lTg" };

function useAction<V>(fn: (v: V) => Promise<unknown>, ok?: string) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => { if (ok) toast.success(ok); qc.invalidateQueries({ queryKey: ["prbc"] }); },
    onError: (e) => toast.error(errorMessage(e)) });
}

export type PrbcView = "control" | "tasks" | "people" | "log" | "settings";

export function PrbcIntegration({ view = "control" }: { view?: PrbcView }) {
  const t = useTranslations("prbc");
  const ov = useQuery({ queryKey: ["prbc", "overview"], queryFn: () => get<Overview>("prbc/overview/"), refetchInterval: 15_000 });
  const sync = useAction(() => api.post("prbc/sync/"), t("syncQueued"));
  const c = ov.data?.connection;
  return (
    <Page>
      <PageHeader title={t(`v_${view}`)} description={t(`v_${view}Desc`)} actions={
        <div className="flex flex-wrap items-center gap-2">
          <span className={cn("hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs sm:flex",
            c?.worker_alive ? "border-success/30 text-success" : "border-destructive/30 text-destructive")}>
            <span className={cn("size-1.5 rounded-full", c?.worker_alive ? "animate-pulse bg-success" : "bg-destructive")} />
            {c?.worker_alive ? t("workerOk") : t("workerDown")}
          </span>
          {c && <span className="hidden text-xs text-muted-foreground md:inline">{t("slaBadge", { n: c.sla_minutes, a: c.work_start, b: c.work_end })}</span>}
          <Button variant="outline" onClick={() => sync.mutate(undefined)} disabled={sync.isPending || c?.sync_requested}>
            <RefreshCcwDot className={cn("size-4", c?.sync_requested && "animate-spin")} />{t("syncNow")}
          </Button>
        </div>} />
      <nav className="mb-5 flex flex-wrap gap-1.5 border-b pb-3">
        {(["control", "tasks", "people", "log", "settings"] as PrbcView[]).map((v) => (
          <Link key={v} href={v === "control" ? "/prbc" : `/prbc/${v}`}
            className={cn("rounded-full border px-3.5 py-1.5 text-sm font-medium transition-colors",
              view === v ? "border-primary bg-primary text-primary-foreground" : "bg-card text-muted-foreground hover:text-foreground")}>
            {t(`v_${v}`)}
          </Link>
        ))}
      </nav>
      {c && !c.ready && (
        <Card className="mb-4 flex-row items-center gap-2 border-warning/40 bg-warning/5 p-3 text-sm text-warning"><CircleAlert className="size-4" />{c.not_ready}</Card>
      )}
      {c?.ready && c.last_error && (
        <Card className="mb-4 flex-row items-center gap-2 border-destructive/30 bg-destructive/5 p-3 text-sm text-destructive"><CircleAlert className="size-4" />{c.last_error}</Card>
      )}
      {view === "control" && <PrbcControl />}
      {view === "tasks" && <TasksTab conn={c} />}
      {view === "people" && (
        <>
          {ov.isPending ? <Skeleton className="h-28 rounded-xl" /> : ov.data && (
            <>
              <div className="mb-1 text-sm text-muted-foreground">{t("lastSync")}: {c?.last_sync_at ? d(c.last_sync_at, true) : t("never")}</div>
              <div className="grid grid-cols-2 gap-4 lg:grid-cols-5">
                <StatCard label={t("total")} value={ov.data.people.total} icon={Users} hint={t("month", ov.data.month)} />
                <StatCard label={t("active")} value={ov.data.people.active ?? 0} icon={CheckCircle2} tone="success" />
                <StatCard label={t("leaving")} value={ov.data.people.leaving ?? 0} icon={UserMinus} tone="warning" />
                <StatCard label={t("left")} value={ov.data.people.left ?? 0} icon={UserMinus} tone="danger" />
                <StatCard label={t("unlinked")} value={ov.data.linked.unlinked} icon={Link2} />
              </div>
              {ov.data.left_members.length > 0 && (
                <Card className="mt-4 gap-1 border-warning/40 bg-warning/5 p-4 text-sm">
                  <div className="font-medium text-warning">{t("leftMembers")}</div>
                  {ov.data.left_members.map((m, i) => <div key={i}>{m.member} <span className="text-muted-foreground">— {m.person}, {d(m.left_on)}</span></div>)}
                </Card>
              )}
            </>
          )}
          <div className="mt-4"><PeopleTab /></div>
        </>
      )}
      {view === "log" && <LogTab runs={ov.data?.runs ?? []} />}
      {view === "settings" && (c ? <ConnTab conn={c} /> : <Skeleton className="h-96 rounded-xl" />)}
    </Page>
  );
}

function PeopleTab() {
  const t = useTranslations("prbc");
  const [filter, setFilter] = useState("all");
  const [q, setQ] = useState("");
  const [linkFor, setLinkFor] = useState<Person | null>(null);
  const [codeFor, setCodeFor] = useState<Person | null>(null);
  const params: Record<string, string> = { q };
  if (filter === "unlinked") params.unlinked = "1";
  else if (filter !== "all") params.status = filter;
  const list = useQuery({ queryKey: ["prbc", "people", params], queryFn: () => get<{ total: number; items: Person[] }>("prbc/people/", params) });
  const left = useAction((v: { id: number; revert?: boolean }) => api.post(`prbc/people/${v.id}/left/`, { revert: v.revert }), t("saved"));
  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        {["all", "active", "leaving", "left", "unlinked"].map((f) => (
          <Button key={f} size="sm" variant={filter === f ? "default" : "outline"} onClick={() => setFilter(f)}>{t(f === "all" ? "all" : f)}</Button>
        ))}
        <div className="relative ml-auto w-72">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="pl-8" />
        </div>
      </div>
      {list.isPending ? <Skeleton className="h-80 rounded-xl" /> : !list.data?.items.length ? <EmptyState icon={Users} title={t("emptyPeople")} /> : (
        <Card className="gap-0 overflow-hidden p-0">
          <Table>
            <TableHeader><TableRow>
              <TableHead>{t("colName")}</TableHead><TableHead>{t("colPosition")}</TableHead><TableHead>{t("colStatus")}</TableHead>
              <TableHead>{t("colLinks")}</TableHead><TableHead className="w-44" />
            </TableRow></TableHeader>
            <TableBody>
              {list.data.items.map((p) => (
                <TableRow key={p.id}>
                  <TableCell><div className="font-medium">{p.full_name}</div>
                    <div className="text-xs text-muted-foreground">{[p.tab_number && `${t("tab")} ${p.tab_number}`, p.phone].filter(Boolean).join(" · ")}</div>
                    <button className="mt-0.5 text-xs text-primary hover:underline" title={t("codeHint")} onClick={() => setCodeFor(p)}>
                      {p.agent_code ? <Badge variant="outline" className="font-mono text-[11px]">{p.agent_code}{p.code_manual ? " ✎" : ""}</Badge> : `+ ${t("agentCode")}`}
                    </button></TableCell>
                  <TableCell className="max-w-64"><div className="truncate">{p.position || "—"}</div><div className="truncate text-xs text-muted-foreground">{p.department || p.company}</div></TableCell>
                  <TableCell>
                    <Badge className={cn("border-0", STATUS_TONE[p.status])}>{t(p.status)}</Badge>
                    {p.status !== "active" && <div className="mt-1 text-xs text-muted-foreground">{t("lastDay")}: {d(p.left_on)}{p.leave_task && ` · ${p.leave_task}`}
                      {p.status === "left" && ` · ${p.left_applied ? t("applied") : t("notApplied")}`}</div>}
                  </TableCell>
                  <TableCell><div className="flex flex-wrap gap-1">
                    {LINKS.map((f) => p.links[f] && <Badge key={f} variant="outline" title={p.links[f]!.label} className="max-w-40 truncate text-[11px]">{t(LINK_KEY[f])}: {p.links[f]!.label}</Badge>)}
                    {p.link_manual && <span className="text-[11px] text-muted-foreground">({t("manual")})</span>}
                  </div></TableCell>
                  <TableCell className="text-right">
                    <div className="flex justify-end gap-1">
                      <Button size="sm" variant="ghost" onClick={() => setLinkFor(p)}><Link2 className="size-4" />{t("link")}</Button>
                      {p.status === "left"
                        ? <Button size="sm" variant="ghost" title={t("revertHint")} onClick={() => left.mutate({ id: p.id, revert: true })}><RotateCcw className="size-4" /></Button>
                        : <Button size="sm" variant="ghost" className="text-destructive" title={t("markLeft")} onClick={() => left.mutate({ id: p.id })}><UserMinus className="size-4" /></Button>}
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      <LinkDialog person={linkFor} onClose={() => setLinkFor(null)} />
      <CodeDialog person={codeFor} onClose={() => setCodeFor(null)} />
    </>
  );
}

function CodeDialog({ person, onClose }: { person: Person | null; onClose: () => void }) {
  const t = useTranslations("prbc");
  const [code, setCode] = useState("");
  const [for_, setFor] = useState<number | null>(null);
  if (person && for_ !== person.id) { setFor(person.id); setCode(person.agent_code); }
  const save = useAction((v: string) => api.patch(`prbc/people/${person!.id}/`, { agent_code: v }), t("saved"));
  return (
    <Dialog open={!!person} onOpenChange={(v) => { if (!v) { setFor(null); onClose(); } }}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader><DialogTitle>{t("agentCode")}</DialogTitle><DialogDescription>{person?.full_name} · {t("codeHint")}</DialogDescription></DialogHeader>
        <Input value={code} onChange={(e) => setCode(e.target.value)} placeholder="Toshkent K1" autoFocus />
        <DialogFooter>
          {person?.code_manual && <Button variant="outline" onClick={() => save.mutate("", { onSuccess: onClose })}>{t("codeAuto")}</Button>}
          <Button disabled={save.isPending} onClick={() => save.mutate(code, { onSuccess: onClose })}>{t("save")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function LinkDialog({ person, onClose }: { person: Person | null; onClose: () => void }) {
  const t = useTranslations("prbc");
  const [field, setField] = useState<LinkField>("staff_person");
  const [q, setQ] = useState("");
  const cands = useQuery({ queryKey: ["prbc", "cand", field, q], queryFn: () => get<Ref[]>("prbc/link-candidates/", { field, q }), enabled: !!person });
  const link = useAction((v: { id: number | null }) => api.post(`prbc/people/${person!.id}/link/`, { field, id: v.id }), t("saved"));
  return (
    <Dialog open={!!person} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader><DialogTitle>{t("linkTitle")}</DialogTitle><DialogDescription>{person?.full_name} · {person?.position}</DialogDescription></DialogHeader>
        <div className="grid gap-3">
          <Select value={field} onValueChange={(v) => setField(v as LinkField)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{LINKS.map((f) => <SelectItem key={f} value={f}>{t(LINK_KEY[f])}{person?.links[f] ? ` — ${person.links[f]!.label}` : ""}</SelectItem>)}</SelectContent>
          </Select>
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("linkSearch")} autoFocus />
          <div className="max-h-64 overflow-y-auto rounded-lg border">
            {(cands.data ?? []).map((c) => (
              <button key={c.id} className="block w-full border-b px-3 py-2 text-left text-sm last:border-0 hover:bg-muted"
                onClick={() => link.mutate({ id: c.id }, { onSuccess: onClose })}>{c.label}</button>
            ))}
          </div>
        </div>
        <DialogFooter>
          {person?.links[field] && <Button variant="outline" className="text-destructive" onClick={() => link.mutate({ id: null }, { onSuccess: onClose })}>{t("unlink")}</Button>}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function TasksTab({ conn }: { conn?: Conn }) {
  const t = useTranslations("prbc");
  const [kind, setKind] = useState("ours");
  const [state, setState] = useState("open");
  const [who, setWho] = useState("");
  const [shown, setShown] = useState<number | null>(null);
  const params: Record<string, string> = { kind: kind === "all" ? "ours,leave,hire" : kind, ...(state !== "all" ? { [state]: "1" } : {}), ...(who ? { assignee: who } : {}) };
  const list = useQuery({ queryKey: ["prbc", "tasks", params], queryFn: () => get<PTask[]>("prbc/tasks/", params), refetchInterval: 30_000 });
  const stats = useQuery({ queryKey: ["prbc", "task-stats"], queryFn: () => get<{ rows: StatRow[]; total: Record<string, number>; groups: GroupRow[] }>("prbc/tasks/stats/", { days: 30 }), refetchInterval: 60_000 });
  const watcherNames = (conn?.task_watchers ?? []).map((id) => conn?.named?.[String(id)] ?? `#${id}`).join(", ");
  const [form, setForm] = useState({ title: "", description: "", assignees: [] as number[], priority: "2", due: "", project: "" });
  const [aq, setAq] = useState("");
  const people = useQuery({ queryKey: ["prbc", "assignable", aq], queryFn: () => get<{ id: number; name: string; position: string }[]>("prbc/assignable/", { q: aq }) });
  const create = useAction(async () => {
    const r = await api.post<PTask>("prbc/tasks/", { title: form.title, description: form.description, assignee_ids: form.assignees,
      priority: Number(form.priority), due_at: form.due ? new Date(`${form.due}T18:00:00`).toISOString() : null, project: form.project || conn?.task_project });
    toast.success(t("created", { code: r.data.code }));
    setForm({ ...form, title: "", description: "", assignees: [] });
  });
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_380px]">
      <div className="min-w-0">
        {stats.data && (
          <Card className="mb-4 gap-0 overflow-hidden p-0">
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-4 py-2.5 text-sm">
              <span className="font-medium">{t("control30")}</span>
              <span className="text-muted-foreground">{t("cTotal", { n: stats.data.total.total ?? 0 })}</span>
              <span className="text-success">{t("cDone", { n: stats.data.total.done ?? 0 })}</span>
              <span className="text-primary">{t("cOpen", { n: stats.data.total.open ?? 0 })}</span>
              <span className="text-destructive">{t("cOverdue", { n: stats.data.total.overdue ?? 0 })}</span>
              {!!stats.data.total.cancelled && <span className="text-muted-foreground">{t("cCancelled", { n: stats.data.total.cancelled })}</span>}
            </div>
            {stats.data.rows.length > 0 && (
              <Table>
                <TableHeader><TableRow>
                  <TableHead>{t("colAssignee")}</TableHead><TableHead className="text-right">{t("colTotal")}</TableHead>
                  <TableHead className="text-right">{t("colDone")}</TableHead><TableHead className="text-right">{t("colOpen")}</TableHead>
                  <TableHead className="text-right">{t("colOverdue")}</TableHead><TableHead className="text-right">{t("colLate")}</TableHead>
                  <TableHead className="text-right">{t("colCancelled")}</TableHead><TableHead className="text-right">{t("colAvg")}</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {stats.data.rows.slice(0, 12).map((r) => (
                    <TableRow key={r.name} className={cn("cursor-pointer", who === r.name && "bg-muted")} onClick={() => setWho(who === r.name ? "" : r.name)}>
                      <TableCell className="max-w-56 truncate">{r.name}</TableCell><TableCell className="text-right">{r.total}</TableCell>
                      <TableCell className="text-right text-success">{r.done}</TableCell><TableCell className="text-right">{r.open}</TableCell>
                      <TableCell className={cn("text-right", r.overdue > 0 && "font-medium text-destructive")}>{r.overdue}</TableCell>
                      <TableCell className="text-right text-warning">{r.late || ""}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{r.cancelled || ""}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{r.avg_hours != null ? t("hours", { n: r.avg_hours }) : "—"}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
            {(stats.data.groups ?? []).length > 0 && (
              <Table>
                <TableHeader><TableRow>
                  <TableHead>{t("colGroup")}</TableHead><TableHead className="text-right">{t("colTotal")}</TableHead>
                  <TableHead className="text-right">{t("colDone")}</TableHead><TableHead className="text-right">{t("colOpen")}</TableHead>
                  <TableHead className="text-right">{t("colOverdue")}</TableHead><TableHead className="text-right">{t("colCancelled")}</TableHead>
                </TableRow></TableHeader>
                <TableBody>
                  {stats.data.groups.slice(0, 15).map((r) => (
                    <TableRow key={r.name}>
                      <TableCell className="max-w-56 truncate">{r.name}</TableCell><TableCell className="text-right">{r.total}</TableCell>
                      <TableCell className="text-right text-success">{r.done}</TableCell><TableCell className="text-right">{r.open}</TableCell>
                      <TableCell className={cn("text-right", r.overdue > 0 && "font-medium text-destructive")}>{r.overdue}</TableCell>
                      <TableCell className="text-right text-muted-foreground">{r.cancelled || ""}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            )}
          </Card>
        )}
        <div className="mb-3 flex flex-wrap items-center gap-2">
          {[["ours", "kindOurs"], ["leave", "kindLeave"], ["hire", "kindHire"], ["all", "all"]].map(([k, l]) => (
            <Button key={k} size="sm" variant={kind === k ? "default" : "outline"} onClick={() => setKind(k)}>{t(l)}</Button>
          ))}
          <div className="ml-auto flex flex-wrap gap-1">
            {[["open", "stOpen"], ["overdue", "stOverdue"], ["done", "stDone"], ["all", "all"]].map(([k, l]) => (
              <Button key={k} size="sm" variant={state === k ? "secondary" : "ghost"} onClick={() => setState(k)}>{t(l)}</Button>
            ))}
          </div>
          {who && <Badge variant="outline" className="cursor-pointer" onClick={() => setWho("")}>{who} ✕</Badge>}
        </div>
        {!list.data?.length ? <EmptyState icon={ListTodo} title={t("noTasks")} /> : (
          <Card className="gap-0 divide-y p-0">
            {list.data.map((x) => (
              <div key={x.id} className="flex cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 px-4 py-2.5 text-sm hover:bg-muted/50" onClick={() => setShown(x.id)}>
                <span className="font-mono text-xs text-muted-foreground">{x.code}</span>
                <span className="min-w-0 flex-1 truncate">{x.title}</span>
                {x.overdue && <Badge className="border-0 bg-destructive/15 text-destructive">{t("overdue")}</Badge>}
                {x.on_time === false && <Badge className="border-0 bg-warning/15 text-warning">{t("late")}</Badge>}
                <Badge variant="outline" className={cn(x.category === "done" && "text-success", x.category === "in_progress" && "text-primary")}>{x.status || "—"}</Badge>
                <div className="w-full pl-0 text-xs text-muted-foreground sm:w-auto">
                  <span title={t("responsible")}>👤 {x.assignee || "—"}</span>
                  {x.watchers && <span title={t("watcher")}> · 👁 {x.watchers}</span>}
                  {x.files > 0 && <span title={t("filesAttached", { n: x.files })}> · 📎 {x.files}</span>}
                  <span> · {x.category === "done" ? `✓ ${d(x.completed_at, true)}${x.completed_by ? ` (${x.completed_by})` : ""}` : d(x.due_at, true)}</span>
                </div>
                <a href={x.url} target="_blank" rel="noreferrer" className="text-primary" title={t("openInPrbc")} onClick={(e) => e.stopPropagation()}><ExternalLink className="size-4" /></a>
              </div>
            ))}
          </Card>
        )}
        <TaskDialog id={shown} onClose={() => setShown(null)} />
      </div>
      <Card className="h-fit gap-3 p-4">
        <div className="font-medium">{t("newTask")}</div>
        <div className="grid gap-1.5"><Label>{t("tTitle")}</Label><Input value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></div>
        <div className="grid gap-1.5"><Label>{t("tDesc")}</Label><Textarea rows={4} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></div>
        <div className="grid gap-1.5"><Label>{t("tAssignees")}</Label>
          <Input value={aq} onChange={(e) => setAq(e.target.value)} placeholder={t("tAssigneesHint")} />
          <div className="max-h-36 overflow-y-auto rounded-lg border text-sm">
            {(people.data ?? []).map((p) => (
              <label key={p.id} className="flex cursor-pointer items-center gap-2 px-2 py-1.5 hover:bg-muted">
                <input type="checkbox" checked={form.assignees.includes(p.id)}
                  onChange={(e) => setForm({ ...form, assignees: e.target.checked ? [...form.assignees, p.id] : form.assignees.filter((x) => x !== p.id) })} />
                <span className="truncate">{p.name}</span><span className="ml-auto truncate text-xs text-muted-foreground">{p.position}</span>
              </label>
            ))}
          </div>
        </div>
        <div className="text-xs text-muted-foreground">👁 {t("watcher")}: {watcherNames || "—"} <span className="opacity-70">({t("fromSettings")})</span></div>
        <div className="grid grid-cols-2 gap-2">
          <div className="grid gap-1.5"><Label>{t("tPriority")}</Label>
            <Select value={form.priority} onValueChange={(v) => setForm({ ...form, priority: v })}>
              <SelectTrigger><SelectValue /></SelectTrigger>
              <SelectContent>{[0, 1, 2, 3, 4].map((n) => <SelectItem key={n} value={String(n)}>{t(`p${n}`)}</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="grid gap-1.5"><Label>{t("tDue")}</Label><Input type="date" value={form.due} onChange={(e) => setForm({ ...form, due: e.target.value })} /></div>
        </div>
        <Button disabled={!form.title.trim() || create.isPending} onClick={() => create.mutate(undefined)}>{t("create")}</Button>
      </Card>
    </div>
  );
}

function TaskDialog({ id, onClose }: { id: number | null; onClose: () => void }) {
  const t = useTranslations("prbc");
  const q = useQuery({ queryKey: ["prbc", "task", id], queryFn: () => get<PTask>(`prbc/tasks/${id}/`), enabled: id != null });
  const x = q.data;
  const r = x?.report;
  const role = (p: TPerson) => t(p.role === "observer" ? "watcher" : p.role === "co_assignee" ? "coAssignee" : "responsible");
  return (
    <Dialog open={id != null} onOpenChange={(v) => !v && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle className="pr-6">{x ? `${x.code} — ${x.title}` : "…"}</DialogTitle>
          <DialogDescription>{x && [x.status, x.project, x.category === "done" ? `✓ ${d(x.completed_at, true)}` : `${t("tDue")}: ${d(x.due_at, true)}`].filter(Boolean).join(" · ")}</DialogDescription>
        </DialogHeader>
        {!x ? <Skeleton className="h-40" /> : (
          <div className="grid gap-4 text-sm">
            <div className="grid gap-1">
              {x.people.length ? x.people.map((p) => (
                <div key={`${p.id}-${p.role}`} className="flex items-center gap-2">
                  <Badge variant="outline" className={cn("w-28 justify-center", p.role === "observer" && "text-primary")}>{role(p)}</Badge>
                  <span>{p.name}</span><span className="truncate text-xs text-muted-foreground">{p.position}</span>
                </div>
              )) : <span className="text-muted-foreground">👤 {x.assignee || "—"}</span>}
            </div>
            {(x.files > 0 || x.notified?.length > 0) && (
              <div className="flex flex-wrap gap-x-4 text-xs text-muted-foreground">
                {x.files > 0 && <span>📎 {t("filesAttached", { n: x.files })}</span>}
                {x.notified?.includes("created") && <span>📌 {t("notifiedCreated")}</span>}
                {x.notified?.includes("done") && <span className="text-success">✅ {t("notifiedDone")}</span>}
              </div>
            )}
            {x.category === "done" && !r && <p className="text-muted-foreground">{t("reportPending")}</p>}
            {r && (
              <>
                <div className="flex flex-wrap gap-x-4 gap-y-1 rounded-lg bg-success/5 p-3">
                  <span>✓ {t("closedBy")}: <b>{r.completed_by || "—"}</b></span>
                  {r.spent_minutes ? <span>⏱ {t("spent", { n: r.spent_minutes })}</span> : null}
                  {r.on_time === true && <span className="text-success">{t("onTime")}</span>}
                  {r.on_time === false && <span className="text-warning">{t("late")}</span>}
                  {x.question && <a className="text-primary hover:underline" href={`/support?q=${x.question}`}>{t("openQuestion")}</a>}
                </div>
                {!!r.comments?.length && (
                  <div className="grid gap-1.5"><div className="font-medium">{t("comments")}</div>
                    {r.comments.map((c, i) => (
                      <div key={i} className="rounded-md border px-3 py-2"><div className="text-xs text-muted-foreground">{c.by} · {d(c.at, true)}</div>
                        <div className="whitespace-pre-wrap">{c.text}</div></div>
                    ))}</div>
                )}
                {!!r.checklist?.length && (
                  <div className="grid gap-1"><div className="font-medium">{t("checklist")}</div>
                    {r.checklist.map((c, i) => (
                      <div key={i}><div className="text-xs text-muted-foreground">{c.title} — {c.done}/{c.total}</div>
                        {c.items.map((it, j) => <div key={j} className={cn("pl-2", it.done ? "text-success" : "text-muted-foreground")}>{it.done ? "☑" : "☐"} {it.text}</div>)}
                      </div>
                    ))}</div>
                )}
                {!!r.worklog?.entries?.length && (
                  <div className="grid gap-1"><div className="font-medium">{t("worklog")}</div>
                    {r.worklog.entries.map((w, i) => <div key={i} className="text-xs">{w.by} — {w.minutes ?? "?"} {t("min")}{w.note && `: ${w.note}`}</div>)}</div>
                )}
                {!!r.history?.length && (
                  <div className="grid gap-0.5"><div className="font-medium">{t("history")}</div>
                    {r.history.map((h, i) => (
                      <div key={i} className="text-xs text-muted-foreground">{d(h.at, true)} · {h.by || "PRBC"} · {h.verb === "status_changed" ? `${String(h.meta.from ?? "")} → ${String(h.meta.to ?? "")}` : h.verb}</div>
                    ))}</div>
                )}
              </>
            )}
          </div>
        )}
        <DialogFooter>{x && <Button variant="outline" asChild><a href={x.url} target="_blank" rel="noreferrer"><ExternalLink className="size-4" />{t("openInPrbc")}</a></Button>}</DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function LogTab({ runs }: { runs: Overview["runs"] }) {
  const t = useTranslations("prbc");
  const ch = useQuery({ queryKey: ["prbc", "changes"], queryFn: () => get<{ id: number; at: string; kind: string; text: string; actor: string }[]>("prbc/changes/") });
  return (
    <div className="grid gap-4 xl:grid-cols-[1fr_360px]">
      <Card className="gap-0 divide-y p-0">
        <div className="px-4 py-2.5 text-sm font-medium">{t("changes")}</div>
        {(ch.data ?? []).map((c) => (
          <div key={c.id} className="flex gap-3 px-4 py-2 text-sm">
            <span className="w-32 shrink-0 text-xs text-muted-foreground">{d(c.at, true)}</span>
            <span className="min-w-0 flex-1">{c.text}</span>
            <span className="text-xs text-muted-foreground">{c.actor}</span>
          </div>
        ))}
      </Card>
      <Card className="h-fit gap-0 divide-y p-0">
        <div className="px-4 py-2.5 text-sm font-medium">{t("runs")}</div>
        {runs.map((r) => (
          <div key={r.id} className="px-4 py-2 text-xs">
            <div className="flex items-center gap-2"><span className={r.ok ? "text-success" : "text-destructive"}>{r.ok ? t("ok") : t("fail")}</span>
              <span className="text-muted-foreground">{d(r.started_at, true)}</span></div>
            <div className="text-muted-foreground">{["new", "updated", "left", "leaving", "returned", "linked", "applied"].map((k) => `${k}: ${String(r.stats?.[k] ?? 0)}`).join(" · ")}</div>
            {r.error && <div className="text-destructive">{r.error}</div>}
          </div>
        ))}
      </Card>
    </div>
  );
}

function ConnTab({ conn }: { conn: Conn }) {
  const t = useTranslations("prbc");
  const [f, setF] = useState({ ...conn, password: "", assignees: conn.task_default_assignees.join(", "), watchers: (conn.task_watchers ?? []).join(", "),
    amap: Object.entries(conn.assignee_map ?? {}).map(([k, v]) => `${k}=${v}`).join(", ") });
  const ids = (s: string) => s.split(/[,\s]+/).filter(Boolean).map(Number).filter((n) => Number.isInteger(n) && n > 0);
  const names = (s: string) => ids(s).map((id) => conn.named?.[String(id)] ?? `#${id}`).join(", ");
  const [test, setTest] = useState<TestResult | null>(null);
  const projects = useQuery({ queryKey: ["prbc", "projects"], queryFn: () => get<Project[]>("prbc/projects/"), enabled: conn.password_set, retry: false });
  const plist: Project[] = test?.projects ?? projects.data ?? [];
  const save = useAction(() => api.patch("prbc/connection/", {
    enabled: f.enabled, base_url: f.base_url, phone: f.phone, sync_minutes: f.sync_minutes, auto_left: f.auto_left,
    comment_devices: f.comment_devices, task_project: f.task_project, lifecycle_project: f.lifecycle_project,
    task_default_assignees: ids(f.assignees), task_watchers: ids(f.watchers), close_on_done: f.close_on_done,
    notify_done: f.notify_done, notify_created: f.notify_created, attach_files: f.attach_files, assignee_map: f.amap,
    watch_self: f.watch_self, outlet_lookup: f.outlet_lookup, sla_minutes: f.sla_minutes, task_priority: f.task_priority,
    work_start: f.work_start, work_end: f.work_end, work_days: f.work_days, sync_status: f.sync_status,
    overdue_alert: f.overdue_alert, task_all_escalated: f.task_all_escalated,
    ...(f.password ? { password: f.password } : {}),
  }), t("saved"));
  const runTest = useAction(async () => {
    const r = await api.post<TestResult>("prbc/connection/test/");
    setTest(r.data);
    toast.success(t("testOk", { name: r.data.me?.full_name ?? "" }));
  });
  return (
    <div className="grid gap-4 lg:grid-cols-[1fr_380px]">
      <Card className="grid gap-4 p-5">
        <p className="rounded-lg bg-muted/50 p-3 text-xs text-muted-foreground">{t("cHelp")}</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <div className="grid gap-1.5"><Label>{t("cPhone")}</Label><Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} placeholder="998901234567" /></div>
          <div className="grid gap-1.5"><Label>{t("cPassword")}</Label>
            <Input type="password" autoComplete="new-password" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
            {conn.password_set && <span className="text-xs text-muted-foreground">{t("cPasswordSet")}</span>}</div>
          <div className="grid gap-1.5"><Label>{t("cBase")}</Label><Input value={f.base_url} onChange={(e) => setF({ ...f, base_url: e.target.value })} /></div>
          <div className="grid gap-1.5"><Label>{t("cMinutes")}</Label><Input type="number" min={5} value={f.sync_minutes} onChange={(e) => setF({ ...f, sync_minutes: Number(e.target.value) })} /></div>
          <div className="grid gap-1.5"><Label>{t("cTaskProject")}</Label>
            <Select value={String(f.task_project ?? "")} onValueChange={(v) => setF({ ...f, task_project: v ? Number(v) : null })}>
              <SelectTrigger><SelectValue placeholder="—" /></SelectTrigger>
              <SelectContent>{plist.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                {f.task_project && !plist.some((p) => p.id === f.task_project) && <SelectItem value={String(f.task_project)}>#{f.task_project}</SelectItem>}</SelectContent>
            </Select>
            <span className="text-xs text-muted-foreground">{plist.length ? t("cProjectHint") : t("cProjectEmpty")}</span></div>
          <div className="grid gap-1.5"><Label>{t("cAssignees")}</Label><Input value={f.assignees} onChange={(e) => setF({ ...f, assignees: e.target.value })} placeholder="48, 167" />
            {f.assignees && <span className="text-xs text-muted-foreground">{names(f.assignees)}</span>}</div>
          <div className="grid gap-1.5"><Label>{t("cWatchers")}</Label><Input value={f.watchers} onChange={(e) => setF({ ...f, watchers: e.target.value })} placeholder="2" />
            <span className="text-xs text-muted-foreground">{f.watchers ? names(f.watchers) : t("cWatchersHint")}</span></div>
          <div className="grid gap-1.5 sm:col-span-2"><Label>{t("cMap")}</Label>
            <Input value={f.amap} onChange={(e) => setF({ ...f, amap: e.target.value })} placeholder="xusniddin_it=60, StargroupSaid=51" />
            <span className="text-xs text-muted-foreground">{t("cMapHint")}</span></div>
        </div>
        {[["enabled", "cEnabled", ""], ["auto_left", "cAutoLeft", "cAutoLeftHint"], ["comment_devices", "cDevices", "cDevicesHint"],
          ["watch_self", "cWatchSelf", "cWatchSelfHint"],
          ["close_on_done", "cCloseDone", "cCloseDoneHint"], ["attach_files", "cAttach", "cAttachHint"],
          ["notify_created", "cNotifyCreated", "cNotifyCreatedHint"], ["notify_done", "cNotifyDone", "cNotifyDoneHint"],
          ["outlet_lookup", "cOutletLookup", "cOutletLookupHint"]].map(([k, l, h]) => (
          <label key={k} className="flex items-start justify-between gap-4 text-sm">
            <span>{t(l)}{h && <span className="block text-xs text-muted-foreground">{t(h, { me: conn.me?.full_name || "—" })}</span>}</span>
            <Switch checked={Boolean(f[k as "enabled"])} onCheckedChange={(v) => setF({ ...f, [k]: v })} />
          </label>
        ))}
        <div className="flex gap-2">
          <Button onClick={() => save.mutate(undefined)} disabled={save.isPending}>{t("save")}</Button>
          <Button variant="outline" onClick={() => runTest.mutate(undefined)} disabled={runTest.isPending}><Plug className="size-4" />{t("test")}</Button>
        </div>
      </Card>
      <SlaCard f={f} setF={setF} onSave={() => save.mutate(undefined)} saving={save.isPending} />
      <GroupProjects projects={plist} className="lg:col-span-2" />
      <OutletCheck className="lg:col-span-2" />
      {test && (
        <Card className="h-fit gap-2 p-5 text-sm">
          <div className="font-medium text-success">{t("testOk", { name: test.me?.full_name ?? "" })}</div>
          {Object.entries(test.checks).map(([k, v]) => (
            <div key={k} className="flex items-center justify-between gap-2">
              <span>{t(`src_${k}`)}</span>
              <span className={v.ok ? "text-success" : "text-muted-foreground"} title={v.detail}>{v.ok ? t("srcOpen", { n: v.count ?? 0 }) : t("srcClosed")}</span>
            </div>
          ))}
        </Card>
      )}
    </div>
  );
}

type SlaFields = Pick<Conn, "sla_minutes" | "task_priority" | "work_start" | "work_end" | "work_days" | "sync_status" | "overdue_alert" | "task_all_escalated">;

/** Vazifa nazorati (SLA): muddat, ish vaqti, ustuvorlik, ikki tomonlama holat, har savolga vazifa. */
function SlaCard<F extends SlaFields>({ f, setF, onSave, saving }: { f: F; setF: (v: F) => void; onSave: () => void; saving: boolean }) {
  const t = useTranslations("prbc");
  const days = f.work_days?.length ? f.work_days : [0, 1, 2, 3, 4, 5];
  const num = (k: keyof SlaFields, v: string) => setF({ ...f, [k]: Number(v) });
  return (
    <Card className="grid h-fit gap-4 p-5">
      <div>
        <div className="flex items-center gap-2 font-medium"><Timer className="size-4 text-primary" />{t("slaTitle")}</div>
        <div className="text-xs text-muted-foreground">{t("slaHint")}</div>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div className="grid gap-1.5"><Label>{t("slaMinutes")}</Label><Input type="number" min={1} value={f.sla_minutes} onChange={(e) => num("sla_minutes", e.target.value)} /></div>
        <div className="grid gap-1.5"><Label>{t("tPriority")}</Label>
          <Select value={String(f.task_priority)} onValueChange={(v) => num("task_priority", v)}>
            <SelectTrigger><SelectValue /></SelectTrigger>
            <SelectContent>{[0, 1, 2, 3, 4].map((n) => <SelectItem key={n} value={String(n)}>{t(`p${n}`)}</SelectItem>)}</SelectContent>
          </Select></div>
        <div className="grid gap-1.5"><Label>{t("slaFrom")}</Label><Input type="number" min={0} max={23} value={f.work_start} onChange={(e) => num("work_start", e.target.value)} /></div>
        <div className="grid gap-1.5"><Label>{t("slaTo")}</Label><Input type="number" min={1} max={24} value={f.work_end} onChange={(e) => num("work_end", e.target.value)} /></div>
      </div>
      <div className="grid gap-1.5"><Label>{t("slaDays")}</Label>
        <div className="flex flex-wrap gap-1">
          {[0, 1, 2, 3, 4, 5, 6].map((n) => (
            <button key={n} type="button" onClick={() => setF({ ...f, work_days: days.includes(n) ? days.filter((x) => x !== n) : [...days, n].sort() })}
              className={cn("h-8 w-10 rounded-md border text-xs font-medium", days.includes(n) ? "border-primary bg-primary text-primary-foreground" : "text-muted-foreground")}>
              {t(`wd${n}`)}
            </button>
          ))}
        </div></div>
      {([["task_all_escalated", "slaAll", "slaAllHint"], ["sync_status", "slaSync", "slaSyncHint"], ["overdue_alert", "slaOverdue", "slaOverdueHint"]] as const).map(([k, l, h]) => (
        <label key={k} className="flex items-start justify-between gap-4 text-sm">
          <span>{t(l)}<span className="block text-xs text-muted-foreground">{t(h)}</span></span>
          <Switch checked={Boolean(f[k])} onCheckedChange={(v) => setF({ ...f, [k]: v })} />
        </label>
      ))}
      <Button onClick={onSave} disabled={saving}>{t("save")}</Button>
    </Card>
  );
}

/** Mijoz arizasining PRBC'dagi holati — bot guruhda beradigan javobning o'zi (STIR / JShShIR / 1C kodi bo'yicha). */
function OutletCheck({ className }: { className?: string }) {
  const t = useTranslations("prbc");
  const [q, setQ] = useState("");
  const [ru, setRu] = useState(false);
  const check = useMutation({
    mutationFn: (v: string) => get<{ ids: string[]; found: number; text: string; text_ru: string; bot_enabled: boolean }>("prbc/outlet-status/", { q: v }),
    onError: (e) => toast.error(errorMessage(e)),
  });
  const r = check.data;
  const text = r ? (ru ? r.text_ru : r.text) : "";
  return (
    <Card className={cn("gap-3 p-5", className)}>
      <div>
        <div className="font-medium">{t("ocTitle")}</div>
        <div className="text-xs text-muted-foreground">{t("ocHint")}</div>
      </div>
      <form className="flex flex-wrap gap-2" onSubmit={(e) => { e.preventDefault(); if (q.trim()) check.mutate(q.trim()); }}>
        <Input className="max-w-sm" value={q} onChange={(e) => setQ(e.target.value)} placeholder="309035202 / UZ-00069292" />
        <Button type="submit" disabled={check.isPending || !q.trim()}><Search className="size-4" />{t("ocCheck")}</Button>
        <Button type="button" variant="ghost" onClick={() => setRu(!ru)}>{ru ? "RU" : "UZ"}</Button>
      </form>
      {r && (
        <>
          {!r.bot_enabled && <p className="text-xs text-warning">{t("ocBotOff")}</p>}
          {text ? <pre className="whitespace-pre-wrap rounded-lg bg-muted/50 p-3 font-sans text-sm">{text.replace(/\*\*/g, "")}</pre>
            : <p className="text-sm text-muted-foreground">{t("ocNone", { ids: r.ids.join(", ") })}</p>}
        </>
      )}
    </Card>
  );
}

function GroupProjects({ projects, className }: { projects: Project[]; className?: string }) {
  const t = useTranslations("prbc");
  const q = useQuery({ queryKey: ["prbc", "group-projects"], queryFn: () => get<{ default: number | null; default_name: string; groups: GroupProject[]; people: { id: number; name: string }[] }>("prbc/group-projects/") });
  const save = useAction((body: Record<string, number | boolean | null>) => api.patch("prbc/group-projects/", body), t("saved"));
  const people = q.data?.people ?? [];
  const refresh = useAction(() => api.get("prbc/projects/", { params: { refresh: 1 } }), t("projectsRefreshed"));
  const rows = q.data?.groups ?? [];
  const sugg = rows.filter((g) => !g.project && g.suggested);
  return (
    <Card className={cn("gap-0 overflow-hidden p-0", className)}>
      <div className="flex flex-wrap items-center gap-2 border-b px-4 py-3">
        <div className="min-w-0 flex-1">
          <div className="font-medium">{t("gpTitle")}</div>
          <div className="text-xs text-muted-foreground">{t("gpHint", { name: q.data?.default_name || (q.data?.default ? `#${q.data.default}` : "—") })}</div>
        </div>
        {sugg.length > 0 && (
          <Button size="sm" variant="outline" disabled={save.isPending}
            onClick={() => save.mutate(Object.fromEntries(sugg.map((g) => [String(g.id), g.suggested])))}>{t("gpApplyAll", { n: sugg.length })}</Button>
        )}
        <Button size="sm" variant="ghost" disabled={refresh.isPending} onClick={() => refresh.mutate(undefined)}>
          <RefreshCcwDot className={cn("size-4", refresh.isPending && "animate-spin")} />{t("gpRefresh")}
        </Button>
      </div>
      {!rows.length ? <div className="px-4 py-6 text-sm text-muted-foreground">{t("gpEmpty")}</div> : (
        <Table>
          <TableHeader><TableRow>
            <TableHead>{t("colGroup")}</TableHead><TableHead className="text-right">{t("gpQuestions")}</TableHead>
            <TableHead title={t("gpTasksHint")}>{t("gpTasks")}</TableHead><TableHead>{t("gpProject")}</TableHead><TableHead>{t("gpOwner")}</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {rows.map((g) => (
              <TableRow key={g.id} className={cn((!g.creates_tasks || g.old) && "opacity-60")}>
                <TableCell className="max-w-64">
                  <div className="truncate">{g.title}</div>
                  {g.old && <div className="truncate text-xs text-warning" title={g.redirect_title}>{t("gpOld", { name: g.redirect_title })}</div>}
                </TableCell>
                <TableCell className="text-right text-muted-foreground">{g.questions}</TableCell>
                <TableCell><Switch checked={g.creates_tasks && !g.old} disabled={save.isPending || g.old} title={g.old ? t("gpOldHint") : undefined}
                  onCheckedChange={(v) => save.mutate({ [`tasks:${g.id}`]: v })} /></TableCell>
                <TableCell>
                  <div className="flex flex-wrap items-center gap-2">
                    <Select value={String(g.project ?? 0)} onValueChange={(v) => save.mutate({ [String(g.id)]: Number(v) || null })}>
                      <SelectTrigger className="h-8 w-64 max-w-full"><SelectValue /></SelectTrigger>
                      <SelectContent>
                        <SelectItem value="0">{t("gpDefault")}</SelectItem>
                        {projects.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                        {g.project && !projects.some((p) => p.id === g.project) && <SelectItem value={String(g.project)}>{g.project_name || `#${g.project}`}</SelectItem>}
                      </SelectContent>
                    </Select>
                    {!g.project && g.suggested && (
                      <button type="button" className="text-xs text-primary hover:underline" onClick={() => save.mutate({ [String(g.id)]: g.suggested })}>
                        {t("gpSuggest", { name: g.suggested_name })}
                      </button>
                    )}
                  </div>
                </TableCell>
                <TableCell>
                  <Select value={String(g.owner ?? 0)} onValueChange={(v) => save.mutate({ [`owner:${g.id}`]: Number(v) || null })}>
                    <SelectTrigger className="h-8 w-56 max-w-full"><SelectValue /></SelectTrigger>
                    <SelectContent>
                      <SelectItem value="0">{g.auto_owner_name ? t("gpOwnerAuto", { name: g.auto_owner_name }) : t("gpOwnerDefault")}</SelectItem>
                      {people.map((p) => <SelectItem key={p.id} value={String(p.id)}>{p.name}</SelectItem>)}
                      {g.owner && !people.some((p) => p.id === g.owner) && <SelectItem value={String(g.owner)}>{g.owner_name || `#${g.owner}`}</SelectItem>}
                    </SelectContent>
                  </Select>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Card>
  );
}
