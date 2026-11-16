"use client";

import { useMutation } from "@tanstack/react-query";
import {
  AlertTriangle, Bot, ChevronDown, ChevronRight, Download, FileJson, FileText, MessageSquareQuote, Pencil, Plus, Search, Sparkles, Star,
} from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";
import { toast } from "sonner";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Page, PageHeader, StatCard } from "@/components/common/page";
import { ZoneIcon } from "@/components/common/zone-icon";
import { askerKey } from "@/components/forms/askers";
import { BotTestDialog } from "@/components/forms/bot-test-dialog";
import { ProcessDialog } from "@/components/forms/structure-dialogs";
import { TaskDialog } from "@/components/forms/task-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useCan, useModel, useScope } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { knowledgeApi } from "@/lib/api/endpoints";
import type { KnowledgeFormat, Process, Task, Zone } from "@/lib/api/types";
import type { Model } from "@/lib/model";
import { cn } from "@/lib/utils";

const norm = (s: string) => s.toLowerCase().replace(/[ʻʼ’‘`´]/g, "'");

type Filter = "all" | "frequent" | "norule";

/**
 * Jarayonlar va savollar bazasi: zona → jarayon → savol turi.
 * Har bir savolda: kim so'raydi → kim javob beradi → kim keyin (qachon), aniq qoida va qanday so'ralishi.
 * Shu ma'lumot AI va Telegram bot uchun eksport qilinadi.
 */
export function Processes() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const { processInScope } = useScope();
  const [query, setQuery] = useState("");
  const [zoneId, setZoneId] = useState<number | "all">("all");
  const [filter, setFilter] = useState<Filter>("all");
  const [editProcess, setEditProcess] = useState<{ process?: Process; zone?: number | null } | null>(null);
  const [editTask, setEditTask] = useState<{ task?: Task; process?: number } | null>(null);
  const [botOpen, setBotOpen] = useState(false);

  const zones = model.state.zones;
  const tasks = model.state.tasks;
  const stats = {
    questions: tasks.length,
    withRule: tasks.filter((x) => x.rule.trim()).length,
    frequent: tasks.filter((x) => x.frequent).length,
    examples: tasks.reduce((n, x) => n + x.examples.length, 0),
  };
  const ready = stats.questions ? Math.round((100 * tasks.filter((x) => x.rule.trim() && x.examples.length).length) / stats.questions) : 0;

  // qidiruv: savol, misollar, qoida, jarayon nomi
  const visible = useMemo(() => {
    const q = norm(query.trim());
    const out = new Map<number, Task[]>();
    for (const p of model.state.processes) {
      if (!processInScope(p.id)) continue;
      if (zoneId !== "all" && p.zone !== zoneId) continue;
      const pText = norm(`${p.name} ${p.description} ${model.systemName(p)}`);
      const list = (model.tasksOf.get(p.id) ?? []).filter((x) => {
        if (filter === "frequent" && !x.frequent) return false;
        if (filter === "norule" && x.rule.trim()) return false;
        return !q || pText.includes(q) || norm(`${x.title} ${x.rule} ${x.examples.join(" ")} ${x.note}`).includes(q);
      });
      if (list.length || (!q && filter === "all")) out.set(p.id, list);
    }
    return out;
  }, [model, query, zoneId, filter, processInScope]);

  const exporter = useMutation({
    mutationFn: ({ fmt, frequent }: { fmt: KnowledgeFormat; frequent: boolean }) => knowledgeApi.export(fmt, frequent),
    onSuccess: (blob, { fmt }) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `savollar-bazasi-${new Date().toISOString().slice(0, 10)}.${fmt === "md" ? "md" : fmt === "json" ? "json" : "jsonl"}`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });

  const zoneList: (Zone | null)[] = [...zones, ...(model.state.processes.some((p) => !p.zone) ? [null] : [])];
  const searching = !!query.trim() || filter !== "all";

  return (
    <Page>
      <PageHeader
        title={t("knowledge.title")}
        description={t("knowledge.description")}
        actions={(
          <>
            <Button variant="outline" onClick={() => setBotOpen(true)}><Bot className="size-4" />{t("knowledge.botTest")}</Button>
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" disabled={exporter.isPending}><Download className="size-4" />{t("knowledge.export")}</Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-72">
                <DropdownMenuLabel>{t("knowledge.exportFor")}</DropdownMenuLabel>
                <DropdownMenuItem onClick={() => exporter.mutate({ fmt: "jsonl", frequent: false })}>
                  <FileJson className="size-4" /><div><div>{t("knowledge.fmt.jsonl")}</div><div className="text-xs text-muted-foreground">{t("knowledge.fmt.jsonlHint")}</div></div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => exporter.mutate({ fmt: "chat", frequent: false })}>
                  <Sparkles className="size-4" /><div><div>{t("knowledge.fmt.chat")}</div><div className="text-xs text-muted-foreground">{t("knowledge.fmt.chatHint")}</div></div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => exporter.mutate({ fmt: "json", frequent: false })}>
                  <FileJson className="size-4" /><div><div>{t("knowledge.fmt.json")}</div><div className="text-xs text-muted-foreground">{t("knowledge.fmt.jsonHint")}</div></div>
                </DropdownMenuItem>
                <DropdownMenuItem onClick={() => exporter.mutate({ fmt: "md", frequent: false })}>
                  <FileText className="size-4" /><div><div>{t("knowledge.fmt.md")}</div><div className="text-xs text-muted-foreground">{t("knowledge.fmt.mdHint")}</div></div>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={() => exporter.mutate({ fmt: "chat", frequent: true })}>
                  <Star className="size-4" />{t("knowledge.fmt.frequentOnly")}
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
            {can.edit && <Button onClick={() => setEditProcess({ zone: zoneId === "all" ? null : zoneId })}><Plus className="size-4" />{t("forms.process.new")}</Button>}
          </>
        )}
      />

      <div className="mb-5 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label={t("knowledge.stats.questions")} value={stats.questions} icon={MessageSquareQuote} />
        <StatCard label={t("knowledge.stats.frequent")} value={stats.frequent} icon={Star} />
        <StatCard label={t("knowledge.stats.withRule")} value={`${stats.withRule}/${stats.questions}`} icon={FileText} tone={stats.withRule < stats.questions ? "warning" : "default"} />
        <Card className="gap-2 p-4">
          <div className="flex items-center gap-2 text-xs text-muted-foreground"><Sparkles className="size-3.5" />{t("knowledge.stats.aiReady")}</div>
          <div className="font-mono text-2xl font-semibold">{ready}%</div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted"><div className="h-full rounded-full bg-gradient-to-r from-primary to-violet" style={{ width: `${ready}%` }} /></div>
          <div className="text-[11px] text-muted-foreground">{t("knowledge.stats.aiReadyHint", { examples: stats.examples })}</div>
        </Card>
      </div>

      {/* zonalar */}
      <div className="mb-4 flex gap-2 overflow-x-auto pb-1">
        <ZoneChip active={zoneId === "all"} onClick={() => setZoneId("all")} label={t("staff.all")} count={model.state.processes.length} />
        {zones.map((z) => (
          <ZoneChip key={z.id} zone={z} active={zoneId === z.id} onClick={() => setZoneId(z.id)} label={z.name}
            count={model.state.processes.filter((p) => p.zone === z.id).length} />
        ))}
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <div className="relative min-w-64 flex-1">
          <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("knowledge.filter")} className="h-10 pl-9" />
        </div>
        {(["all", "frequent", "norule"] as Filter[]).map((f) => (
          <Button key={f} variant={filter === f ? "default" : "outline"} onClick={() => setFilter(f)}>
            {f === "frequent" && <Star className="size-4" />}{f === "norule" && <AlertTriangle className="size-4" />}{t(`knowledge.filters.${f}`)}
          </Button>
        ))}
      </div>

      <div className="space-y-10">
        {zoneList.filter((z) => zoneId === "all" || z?.id === zoneId).map((z) => {
          const procs = model.state.processes.filter((p) => (z ? p.zone === z.id : !p.zone) && visible.has(p.id));
          if (!procs.length) return null;
          const qCount = procs.reduce((n, p) => n + (visible.get(p.id)?.length ?? 0), 0);
          return (
            <section key={z?.id ?? "none"}>
              <div className="mb-4 flex flex-wrap items-center gap-3">
                <ZoneIcon zone={z ?? undefined} size={44} />
                <div className="min-w-0 flex-1">
                  <h2 className="text-lg font-semibold">{z?.name ?? t("knowledge.noZone")}</h2>
                  {z?.description && <p className="max-w-3xl text-sm text-muted-foreground">{z.description}</p>}
                </div>
                <span className="text-xs text-muted-foreground">{t("knowledge.zoneMeta", { processes: procs.length, questions: qCount })}</span>
                {can.edit && <Button variant="ghost" size="sm" onClick={() => setEditProcess({ zone: z?.id ?? null })}><Plus className="size-4" />{t("forms.process.new")}</Button>}
              </div>
              <div className="grid gap-3 xl:grid-cols-2">
                {procs.map((p) => (
                  <ProcessCard
                    key={p.id} process={p} zone={z} tasks={visible.get(p.id) ?? []} model={model} canEdit={can.edit} expanded={searching}
                    onEdit={() => setEditProcess({ process: p })}
                    onEditTask={(task) => setEditTask({ task })}
                    onAddTask={() => setEditTask({ process: p.id })}
                  />
                ))}
              </div>
            </section>
          );
        })}
        {!visible.size && <p className="py-10 text-center text-sm text-muted-foreground">{t("common.nothingFound")}</p>}
      </div>

      <ProcessDialog open={!!editProcess} onOpenChange={(o) => !o && setEditProcess(null)} process={editProcess?.process} zone={editProcess?.zone} />
      <TaskDialog open={!!editTask} onOpenChange={(o) => !o && setEditTask(null)} task={editTask?.task} preset={editTask?.process ? { process: editTask.process } : undefined} />
      <BotTestDialog open={botOpen} onOpenChange={setBotOpen} />
    </Page>
  );
}

function ZoneChip({ zone, active, onClick, label, count }: { zone?: Zone; active: boolean; onClick: () => void; label: string; count: number }) {
  return (
    <button
      type="button" onClick={onClick}
      className={cn("flex shrink-0 items-center gap-2 rounded-xl border bg-card py-1.5 pl-1.5 pr-3 text-sm transition-colors hover:border-primary/40",
        active && "border-primary bg-primary/10 text-primary")}
    >
      {zone ? <ZoneIcon zone={zone} size={26} className="rounded-lg" /> : <span className="w-1" />}
      <span className="font-medium">{label}</span>
      <span className="font-mono text-xs text-muted-foreground">{count}</span>
    </button>
  );
}

function ProcessCard({ process: p, zone, tasks, model, canEdit, expanded, onEdit, onEditTask, onAddTask }: {
  process: Process; zone: Zone | null; tasks: Task[]; model: Model; canEdit: boolean; expanded: boolean;
  onEdit: () => void; onEditTask: (t: Task) => void; onAddTask: () => void;
}) {
  const t = useTranslations();
  const [open, setOpen] = useState(false);
  const show = open || expanded;
  const level = model.level(p.id);
  const owners = (model.rolesOf.get(p.id) ?? []).filter((r) => r.role === "owner").map((r) => model.member.get(r.member)).filter((m) => !!m);
  const frequent = tasks.filter((x) => x.frequent).length;
  const color = zone?.color ?? "#64748B";
  return (
    <Card className="gap-0 overflow-hidden p-0" style={{ borderTop: `3px solid ${color}` }}>
      <div className="flex items-start gap-3 px-4 py-3">
        <button type="button" onClick={() => setOpen((v) => !v)} className="mt-0.5 text-muted-foreground hover:text-foreground" aria-label="toggle">
          {show ? <ChevronDown className="size-4" /> : <ChevronRight className="size-4" />}
        </button>
        <div className="min-w-0 flex-1 cursor-pointer" onClick={() => setOpen((v) => !v)}>
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-semibold">{p.name}</h3>
            {model.systemName(p) && <Badge variant="outline" className="text-[10.5px]">{model.systemName(p)}</Badge>}
            {level && <span className={cn("size-2 rounded-full", level === "danger" ? "bg-destructive" : "bg-warning")} title={(model.issues.get(p.id) ?? []).map((i) => t(`issues.${i.code}`, { count: i.count ?? 0 })).join(", ")} />}
          </div>
          {p.description && <p className="mt-0.5 text-xs text-muted-foreground">{p.description}</p>}
          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              {owners.slice(0, 3).map((m) => <MemberAvatar key={m.id} member={m} size={20} />)}
              {owners.length ? owners.map((m) => m.name).join(", ") : <span className="text-destructive">{t("org.noOwner")}</span>}
            </span>
            <span>{t("knowledge.questionsCount", { count: tasks.length })}</span>
            {!!frequent && <span className="flex items-center gap-1 text-warning"><Star className="size-3 fill-current" />{frequent}</span>}
          </div>
        </div>
        {canEdit && <Button variant="ghost" size="icon" className="size-8 shrink-0" onClick={onEdit} aria-label={t("common.edit")}><Pencil className="size-4" /></Button>}
      </div>
      {show && (
        <div className="divide-y border-t bg-muted/20">
          {tasks.map((task) => <QuestionRow key={task.id} task={task} model={model} canEdit={canEdit} onEdit={() => onEditTask(task)} />)}
          {canEdit && (
            <button type="button" onClick={onAddTask} className="flex w-full items-center gap-2 px-4 py-2.5 text-sm text-muted-foreground hover:bg-muted/50 hover:text-foreground">
              <Plus className="size-4" />{t("knowledge.addQuestion")}
            </button>
          )}
        </div>
      )}
    </Card>
  );
}

/** Savol: kim so'raydi → kim javob beradi → keyingi navbat (qachon); ochilsa — qoida va misollar. */
function QuestionRow({ task, model, canEdit, onEdit }: { task: Task; model: Model; canEdit: boolean; onEdit: () => void }) {
  const t = useTranslations();
  const [open, setOpen] = useState(false);
  const owner = task.owner ? model.member.get(task.owner) : undefined;
  const hasDetails = !!task.rule || !!task.examples.length || task.fallbacks.some((f) => f.condition);
  return (
    <div className="group px-4 py-2.5">
      <div className="flex items-start gap-2">
        <button type="button" onClick={() => setOpen((v) => !v)} className={cn("mt-0.5 text-muted-foreground", !hasDetails && "invisible")} aria-label="details">
          {open ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-1.5 text-[13.5px] font-medium">
            {task.frequent && <Star className="size-3.5 shrink-0 fill-warning text-warning" />}
            <span className="cursor-pointer" onClick={() => setOpen((v) => !v)}>{task.title}</span>
            {!task.rule && <span className="rounded border border-dashed px-1 text-[10px] font-normal text-muted-foreground">{t("knowledge.noRule")}</span>}
          </div>
          {/* zanjir */}
          <div className="mt-1.5 flex flex-wrap items-center gap-1 text-[11.5px]">
            {task.asker && <span className="rounded-full bg-muted px-2 py-0.5 text-muted-foreground">{t(`knowledge.askers.${askerKey(task.asker)}`)}</span>}
            {task.asker && <span className="text-muted-foreground">→</span>}
            <Person name={owner?.name ?? t("common.unassigned")} member={owner} primary />
            {task.fallbacks.map((f, i) => (
              <span key={i} className="flex items-center gap-1">
                <span className="text-muted-foreground">→</span>
                <Person name={model.member.get(f.member)?.name ?? "?"} member={model.member.get(f.member)} hint={f.condition} />
              </span>
            ))}
          </div>
        </div>
        {canEdit && <Button variant="ghost" size="icon" className="size-7 shrink-0 opacity-0 group-hover:opacity-100" onClick={onEdit} aria-label={t("common.edit")}><Pencil className="size-3.5" /></Button>}
      </div>
      {open && (
        <div className="mt-2.5 ml-5 space-y-2.5">
          {task.rule && (
            <div className="rounded-lg border-l-[3px] border-primary bg-card px-3 py-2">
              <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-primary">{t("knowledge.rule")}</div>
              <p className="whitespace-pre-line text-[13px] leading-relaxed">{task.rule}</p>
            </div>
          )}
          {task.fallbacks.some((f) => f.condition) && (
            <ol className="space-y-1 text-[12.5px]">
              {task.fallbacks.map((f, i) => f.condition && (
                <li key={i} className="flex gap-2">
                  <span className="grid size-5 shrink-0 place-items-center rounded-full bg-muted font-mono text-[10px]">{i + 2}</span>
                  <span><b className="font-medium">{model.member.get(f.member)?.name}</b> — <span className="text-muted-foreground">{f.condition}</span></span>
                </li>
              ))}
            </ol>
          )}
          {!!task.examples.length && (
            <div>
              <div className="mb-1 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">{t("knowledge.examples")}</div>
              <div className="flex flex-wrap gap-1.5">
                {task.examples.map((e) => <span key={e} className="rounded-full border bg-card px-2.5 py-0.5 text-xs italic text-muted-foreground">“{e}”</span>)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Person({ name, member, primary, hint }: { name: string; member?: Parameters<typeof MemberAvatar>[0]["member"]; primary?: boolean; hint?: string }) {
  return (
    <span
      title={hint}
      className={cn("inline-flex items-center gap-1 rounded-full border py-0.5 pl-0.5 pr-2", primary ? "border-primary/40 bg-primary/10 font-medium text-primary" : "bg-card text-muted-foreground")}
    >
      <MemberAvatar member={member} size={16} />{name}
      {hint && <span className="size-1.5 rounded-full bg-warning" />}
    </span>
  );
}
