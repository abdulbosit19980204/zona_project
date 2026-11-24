"use client";

import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, ExternalLink, FlaskConical, ListTodo, Paperclip, RotateCcw, Save, SkipForward, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { cn } from "@/lib/utils";

import { supportApi, type SupportSettings, type SupportTaskInfo, type TasksPayload } from "./api";
import { fmtDate, Metric, Panel, SearchPicker, Segmented, useSupportMutation } from "./common";
import type { SKey, ST } from "./i18n";
import { SettingRow } from "./shell";

const TONE: Record<SupportTaskInfo["status"], string> = {
  queued: "border-warning/40 text-warning", sent: "border-success/40 text-success", reminded: "border-primary/40 text-primary",
  failed: "border-destructive/40 text-destructive", skipped: "text-muted-foreground", done: "border-success bg-success/10 text-success",
};

/** PRBC vazifalari: qachon yaratiladi, kimga, va yaratilgan vazifalar tarixi (savol beruvchilarga ko'rinmaydi). */
export function TasksPanel({ t }: { t: ST }) {
  const st = useQuery({ queryKey: ["support", "settings"], queryFn: supportApi.settings });
  const [status, setStatus] = useState("all");
  const data = useQuery({ queryKey: ["support", "tasks", status], queryFn: () => supportApi.tasks(status), refetchInterval: 15_000 });
  if (!st.data || !data.data) return <Skeleton className="h-96" />;
  return (
    <div className="grid gap-4">
      <TaskSettings key={st.dataUpdatedAt} s={st.data} d={data.data} t={t} />
      <Panel title={t("tkHistory")} icon={ListTodo} bodyClassName="grid gap-3"
        actions={<Segmented size="sm" value={status} onChange={setStatus} options={[
          { value: "all", label: t("all") },
          { value: "queued", label: t("ts_queued"), count: data.data.counts.queued },
          { value: "sent", label: t("ts_sent") },
          { value: "reminded", label: t("ts_reminded") },
          { value: "done", label: t("ts_done") },
          { value: "failed", label: t("ts_failed"), count: data.data.counts.failed },
          { value: "skipped", label: t("ts_skipped") },
        ]} />}>
        {data.data.tasks.length === 0 && <p className="text-sm text-muted-foreground">{t("tkNone")}</p>}
        {data.data.tasks.map((x) => <TaskRow key={x.id} x={x} t={t} />)}
      </Panel>
    </div>
  );
}

function TaskSettings({ s, d, t }: { s: SupportSettings; d: TasksPayload; t: ST }) {
  const [f, setF] = useState({
    tasks_enabled: s.tasks_enabled, task_bot: s.task_bot, task_default_assignee: s.task_default_assignee,
    task_departments: s.task_departments ?? [], task_members: s.task_members ?? [], task_daily_limit: s.task_daily_limit,
    task_gap: s.task_gap, task_attach: s.task_attach, task_mode: s.task_mode ?? "command",
    task_remind_group: s.task_remind_group ?? true, task_remind_dm: s.task_remind_dm ?? true,
  });
  const mode = f.tasks_enabled ? f.task_mode : "off";
  const setMode = (v: string) => setF(v === "off" ? { ...f, tasks_enabled: false } : { ...f, tasks_enabled: true, task_mode: v as "command" | "remind" | "account" | "api" });
  const [testTo, setTestTo] = useState(s.task_default_assignee || "");
  const [pick, setPick] = useState("");
  const save = useSupportMutation(() => supportApi.saveSettings({ ...f, task_bot: f.task_bot.replace(/^@/, ""),
    task_default_assignee: f.task_default_assignee.replace(/^@/, "") }), t("saved"));
  const test = useSupportMutation(() => supportApi.taskTest(testTo), t("tkTestQueued"));
  const toggleDep = (id: number) => setF({ ...f, task_departments: f.task_departments.includes(id)
    ? f.task_departments.filter((x) => x !== id) : [...f.task_departments, id] });
  const memberName = (id: number) => d.members.find((m) => m.id === id)?.name ?? `#${id}`;

  return (
    <>
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Metric label={t("tkSentToday")} value={d.sent_today} hint={t("tkLimit", { n: f.task_daily_limit })} icon={CheckCircle2} tone="success" />
        <Metric label={t("ts_queued")} value={d.counts.queued ?? 0} icon={ListTodo} tone="primary" />
        <Metric label={t("ts_failed")} value={d.counts.failed ?? 0} icon={AlertTriangle} tone={(d.counts.failed ?? 0) ? "warning" : undefined} />
        <Link href="/support/knowledge" className="rounded-xl outline-none hover:opacity-90">
          <Metric label={t("tkEntries")} value={d.entries_with_task} hint={t("tkEntriesHint")} icon={ListTodo} />
        </Link>
      </div>

      <Panel title={t("tkMode")} icon={ListTodo} bodyClassName="grid gap-3">
        <Segmented value={mode} onChange={setMode} options={[
          { value: "off", label: t("tkModeOff") },
          { value: "api", label: t("tkModeApi") },
          { value: "command", label: t("tkModeCommand") },
          { value: "remind", label: t("tkModeRemind") },
          { value: "account", label: t("tkModeAccount") },
        ]} />
        <p className={cn("rounded-lg p-3 text-sm", mode === "account" ? "border border-warning/40 bg-warning/10 text-warning" : "bg-muted/50 text-muted-foreground")}>
          {t(mode === "off" ? "tkModeOffHint" : mode === "api" ? "tkModeApiHint" : mode === "command" ? "tkModeCommandHint" : mode === "remind" ? "tkModeRemindHint" : "tkModeAccountHint")}
        </p>
        {mode === "api" && <Link href="/prbc" className="text-sm text-primary hover:underline">{t("tkModeApiLink")} →</Link>}
        {mode === "command" && (
          <div className="grid gap-1.5 rounded-lg border border-primary/30 bg-primary/5 p-3 text-sm">
            <b>{t("tkCmdSetupTitle")}</b>
            <ol className="list-decimal space-y-1 pl-5 text-xs text-muted-foreground">
              <li>{t("tkCmdSetup1")}</li><li>{t("tkCmdSetup2")}</li><li>{t("tkCmdSetup3")}</li>
            </ol>
            <code className="mt-1 rounded bg-background px-2 py-1 text-xs">/vazifa@{f.task_bot || "prbc_bot"} @StargroupSaid {t("tkCmdExample")}</code>
          </div>
        )}
        {mode === "remind" && (
          <div className="grid gap-0">
            <SettingRow label={t("tkRemindDm")} hint={t("tkRemindDmHint")}>
              <Switch checked={f.task_remind_dm} onCheckedChange={(v) => setF({ ...f, task_remind_dm: v })} />
            </SettingRow>
            <SettingRow label={t("tkRemindGroup")} hint={t("tkRemindGroupHint")}>
              <Switch checked={f.task_remind_group} onCheckedChange={(v) => setF({ ...f, task_remind_group: v })} />
            </SettingRow>
          </div>
        )}
      </Panel>

      {mode === "account" && !s.mtproto_connected && (
        <p className="rounded-lg border border-warning/40 bg-warning/10 p-3 text-sm text-warning">{t("tkNeedAccount")}</p>
      )}

      <div className="grid gap-4 xl:grid-cols-2">
        <Panel title={t("tkHow")} hint={t(mode === "account" ? "tkHowHint" : "tkHowRemind")} icon={ListTodo} bodyClassName="grid gap-0">
          {mode === "command" && (
            <SettingRow label={t("tkBot")} hint={t("tkBotCmdHint")}>
              <Input className="w-44" value={f.task_bot} placeholder="prbc_bot" onChange={(e) => setF({ ...f, task_bot: e.target.value })} />
            </SettingRow>
          )}
          {mode === "account" && (
            <>
              <SettingRow label={t("tkAttach")} hint={t("tkAttachHint")}>
                <Switch checked={f.task_attach} onCheckedChange={(v) => setF({ ...f, task_attach: v })} />
              </SettingRow>
              <SettingRow label={t("tkBot")} hint={t("tkBotHint")}>
                <Input className="w-44" value={f.task_bot} placeholder="prbc_bot" onChange={(e) => setF({ ...f, task_bot: e.target.value })} />
              </SettingRow>
            </>
          )}
          <SettingRow label={t("tkDefault")} hint={t("tkDefaultHint")}>
            <Input className="w-44" value={f.task_default_assignee} placeholder="@username" onChange={(e) => setF({ ...f, task_default_assignee: e.target.value })} />
          </SettingRow>
          {mode === "account" && (
            <SettingRow label={t("tkDaily")} hint={t("tkGapHint", { n: f.task_gap })}>
              <div className="flex gap-2">
                <Input className="w-20" type="number" min={1} value={f.task_daily_limit} onChange={(e) => setF({ ...f, task_daily_limit: Number(e.target.value) || 1 })} />
                <Input className="w-20" type="number" min={5} value={f.task_gap} onChange={(e) => setF({ ...f, task_gap: Number(e.target.value) || 5 })} />
              </div>
            </SettingRow>
          )}
        </Panel>

        <Panel title={t("tkWhom")} hint={t("tkWhomHint")} icon={ListTodo} bodyClassName="grid gap-4">
          <div className="grid gap-2">
            <div className="text-xs font-medium text-muted-foreground">{t("tkDeps")}</div>
            <div className="flex flex-wrap gap-1.5">
              {d.departments.map((x) => {
                const on = f.task_departments.includes(x.id);
                return (
                  <button key={x.id} type="button" onClick={() => toggleDep(x.id)}
                    className={cn("rounded-full border px-3 py-1 text-xs transition-colors", on ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>
                    {x.name}
                  </button>
                );
              })}
            </div>
          </div>
          <div className="grid gap-2">
            <div className="text-xs font-medium text-muted-foreground">{t("tkMembers")}</div>
            <div className="flex flex-wrap gap-1.5">
              {f.task_members.map((id) => (
                <span key={id} className="inline-flex items-center gap-1 rounded-full border bg-muted/50 py-0.5 pl-2.5 pr-1 text-xs">
                  {memberName(id)}
                  <button type="button" aria-label={t("delete")} className="grid size-4 place-items-center rounded-full hover:bg-destructive hover:text-white"
                    onClick={() => setF({ ...f, task_members: f.task_members.filter((x) => x !== id) })}><X className="size-3" /></button>
                </span>
              ))}
            </div>
            <SearchPicker value={pick} className="w-full"
              onChange={(v) => { setPick(""); if (!f.task_members.includes(Number(v))) setF({ ...f, task_members: [...f.task_members, Number(v)] }); }}
              options={d.members.map((m) => ({ id: m.id, title: m.name, sub: [m.department, m.telegram && `@${m.telegram}`, m.is_team && t("team")].filter(Boolean).join(" · ") }))}
              placeholder={t("tkAddMember")} searchPlaceholder={t("search")} emptyText={t("pickNone")} />
          </div>
          <p className="text-xs text-muted-foreground">{t("tkRuleNote")}</p>
        </Panel>
      </div>

      <div className="flex flex-wrap items-end gap-2">
        <Button disabled={save.isPending} onClick={() => save.mutate(undefined)}><Save className="size-4" />{t("save")}</Button>
        {mode === "account" && <div className="ml-auto flex flex-wrap items-center gap-2 rounded-lg border bg-card p-2">
          <span className="text-xs text-muted-foreground">{t("tkTest")}</span>
          <Input className="h-8 w-40" value={testTo} placeholder="@username" onChange={(e) => setTestTo(e.target.value)} />
          <Button size="sm" variant="outline" disabled={!testTo.trim() || test.isPending || !s.mtproto_connected} onClick={() => test.mutate(undefined)}>
            <FlaskConical className="size-4" />{t("tkTestBtn")}
          </Button>
        </div>}
      </div>
    </>
  );
}

function TaskRow({ x, t }: { x: SupportTaskInfo; t: ST }) {
  const [open, setOpen] = useState(false);
  const [who, setWho] = useState(x.assignee);
  const retry = useSupportMutation(() => supportApi.taskAction(x.id, "retry", who !== x.assignee ? who : undefined), t("saved"));
  const skip = useSupportMutation(() => supportApi.taskAction(x.id, "skip"), t("saved"));
  return (
    <div className="rounded-lg border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant="outline" className={cn("font-normal", TONE[x.status])}>{t(`ts_${x.status}` as SKey)}</Badge>
        <button type="button" className="min-w-0 flex-1 truncate text-left text-sm font-medium hover:text-primary" onClick={() => setOpen(!open)}>
          {x.title || "—"}
        </button>
        {x.assignee && <span className="text-xs text-muted-foreground">@{x.assignee}</span>}
        {x.files > 0 && <span className="inline-flex items-center gap-0.5 text-xs text-muted-foreground"><Paperclip className="size-3" />{x.files}</span>}
        {x.duplicates > 0 && <span className="text-xs text-muted-foreground">+{x.duplicates} {t("tkDup")}</span>}
        <span className="text-[11px] text-muted-foreground">{fmtDate(x.created_at)}</span>
      </div>
      <div className="mt-1 flex flex-wrap gap-x-3 text-xs text-muted-foreground">
        {x.asker && <span>{x.asker}</span>}{x.group && <span>· {x.group}</span>}
        <span>· {x.reason === "entry" ? t("tkByEntry") : x.reason === "test" ? t("tkByTest") : x.reason.replace("responsible:", t("tkByResp") + ": ")}</span>
        {x.link && <a className="inline-flex items-center gap-0.5 text-primary hover:underline" href={x.link} target="_blank" rel="noreferrer">Telegram<ExternalLink className="size-3" /></a>}
      </div>
      {x.reply && <p className="mt-2 rounded-md bg-muted/60 p-2 text-xs"><b>PRBC:</b> {x.reply}</p>}
      {x.error && <p className="mt-2 text-xs text-destructive">{x.error}</p>}
      {open && <pre className="mt-2 max-h-56 overflow-auto whitespace-pre-wrap rounded-md border bg-background p-2 text-xs">{x.text}</pre>}
      {(x.status === "failed" || x.status === "skipped" || x.status === "queued") && (
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Input className="h-8 w-40" value={who} onChange={(e) => setWho(e.target.value.replace(/^@/, ""))} placeholder="username" />
          {x.status !== "queued" && <Button size="sm" variant="outline" disabled={retry.isPending || !who} onClick={() => retry.mutate(undefined)}><RotateCcw className="size-4" />{t("tkRetry")}</Button>}
          {x.status === "queued" && <Button size="sm" variant="ghost" disabled={skip.isPending} onClick={() => skip.mutate(undefined)}><SkipForward className="size-4" />{t("tkSkip")}</Button>}
        </div>
      )}
    </div>
  );
}
