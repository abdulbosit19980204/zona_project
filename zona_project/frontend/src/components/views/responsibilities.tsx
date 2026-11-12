"use client";

import { GitPullRequestArrow, KanbanSquare, List, Pencil, Plus, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Page, PageHeader } from "@/components/common/page";
import { fromId, NONE, toId } from "@/components/forms/form-kit";
import { ProposeDialog } from "@/components/forms/propose-dialog";
import { TaskDialog } from "@/components/forms/task-dialog";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useCan, useModel, useOrgMutation, useScope } from "@/hooks/use-org";
import { orgApi } from "@/lib/api/endpoints";
import type { Task } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const norm = (s: string) => s.toLowerCase().replace(/[ʻʼ’‘`´]/g, "'");

export function Responsibilities() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const { inScope, scope } = useScope();
  const [mode, setMode] = useState<"table" | "board">("table");
  const [query, setQuery] = useState("");
  const [system, setSystem] = useState(NONE);
  const [owner, setOwner] = useState("all");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [bulkOwner, setBulkOwner] = useState(NONE);
  const [edit, setEdit] = useState<Task | null | undefined>(undefined);
  const [propose, setPropose] = useState<Task | null>(null);
  const [dragging, setDragging] = useState<number | null>(null);
  const [over, setOver] = useState<number | null>(null);

  const move = useOrgMutation(({ id, to }: { id: number; to: number | null }) => orgApi.tasks.move(id, to), t("responsibilities.moved"));
  const bulk = useOrgMutation(({ ids, to }: { ids: number[]; to: number | null }) => orgApi.tasks.bulkMove(ids, to),
    (r) => t("responsibilities.bulkMoved", { count: r.moved }));

  const visible = useMemo(() => {
    const q = norm(query.trim());
    return model.state.tasks.filter((task) => {
      const m = task.owner ? model.member.get(task.owner) : undefined;
      if (scope && (!m || !inScope(m))) return false;
      const p = task.process ? model.process.get(task.process) : undefined;
      if (system !== NONE && String(p?.system ?? "") !== system) return false;
      if (owner === "none" && task.owner) return false;
      if (owner !== "all" && owner !== "none" && String(task.owner) !== owner) return false;
      return !q || norm(`${task.title} ${p?.name ?? ""} ${model.systemName(p)} ${task.note}`).includes(q);
    });
  }, [model, query, system, owner, scope, inScope]);

  // Barqaror obyekt: aks holda dialog har renderda formani qayta tiklaydi.
  const proposePreset = useMemo(
    () => (propose ? { kind: "task_owner" as const, task: String(propose.id), owner: fromId(propose.owner) } : undefined),
    [propose],
  );

  const changeOwner =(task: Task, value: string) => {
    if (can.edit) move.mutate({ id: task.id, to: toId(value) });
  };
  const columns = [...model.memberOrder.filter(inScope).map((m) => ({ id: m.id as number | null, member: m })), ...(scope ? [] : [{ id: null, member: undefined }])];

  return (
    <Page>
      <PageHeader
        title={t("nav.responsibilities")}
        description={t("responsibilities.description")}
        actions={<>
          <ToggleGroup type="single" variant="outline" value={mode} onValueChange={(v) => v && setMode(v as "table" | "board")}>
            <ToggleGroupItem value="table" aria-label={t("responsibilities.table")}><List className="size-4" />{t("responsibilities.table")}</ToggleGroupItem>
            <ToggleGroupItem value="board" aria-label={t("responsibilities.board")}><KanbanSquare className="size-4" />{t("responsibilities.board")}</ToggleGroupItem>
          </ToggleGroup>
          {can.edit && <Button onClick={() => setEdit(null)}><Plus className="size-4" />{t("forms.task.new")}</Button>}
        </>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-72"><Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("responsibilities.filter")} className="pl-8" /></div>
        <Select value={system} onValueChange={setSystem}>
          <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={NONE}>{t("responsibilities.allSystems")}</SelectItem>
            {model.state.systems.map((s) => <SelectItem key={s.id} value={String(s.id)}>{s.name}</SelectItem>)}
          </SelectContent>
        </Select>
        {mode === "table" && (
          <Select value={owner} onValueChange={setOwner}>
            <SelectTrigger className="w-56"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value="all">{t("responsibilities.allOwners")}</SelectItem>
              <SelectItem value="none">{t("common.unassigned")}</SelectItem>
              {model.memberOrder.map((m) => <SelectItem key={m.id} value={String(m.id)}>{m.name}</SelectItem>)}
            </SelectContent>
          </Select>
        )}
        <span className="text-sm text-muted-foreground">{t("responsibilities.shown", { shown: visible.length, total: model.state.tasks.length })}</span>
      </div>

      {mode === "table" && can.edit && selected.size > 0 && (
        <div className="mb-3 flex items-center gap-3 rounded-xl border border-primary/40 bg-primary/10 px-4 py-2.5 text-sm">
          <b>{t("responsibilities.selected", { count: selected.size })}</b>
          <Select value={bulkOwner} onValueChange={setBulkOwner}>
            <SelectTrigger size="sm" className="w-64 bg-card"><SelectValue /></SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t("common.unassigned")}</SelectItem>
              {model.memberOrder.map((m) => <SelectItem key={m.id} value={String(m.id)}>{m.name}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button size="sm" disabled={bulk.isPending} onClick={() => bulk.mutate({ ids: [...selected], to: toId(bulkOwner) }, { onSuccess: () => setSelected(new Set()) })}>
            {t("responsibilities.moveSelected")}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setSelected(new Set())}>{t("common.cancel")}</Button>
        </div>
      )}

      {mode === "table" ? (
        <Card className="gap-0 overflow-hidden p-0">
          <Table>
            <TableHeader>
              <TableRow>
                {can.edit && (
                  <TableHead className="w-10">
                    <Checkbox
                      checked={visible.length > 0 && visible.every((x) => selected.has(x.id))}
                      onCheckedChange={(v) => setSelected(v === true ? new Set(visible.map((x) => x.id)) : new Set())}
                    />
                  </TableHead>
                )}
                <TableHead>{t("forms.task.title")}</TableHead>
                <TableHead>{t("forms.task.process")}</TableHead>
                <TableHead className="w-64">{t("forms.task.owner")}</TableHead>
                <TableHead className="w-12" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {visible.map((task) => {
                const p = task.process ? model.process.get(task.process) : undefined;
                const m = task.owner ? model.member.get(task.owner) : undefined;
                return (
                  <TableRow key={task.id}>
                    {can.edit && (
                      <TableCell>
                        <Checkbox checked={selected.has(task.id)} onCheckedChange={(v) => setSelected((s) => { const n = new Set(s); if (v === true) n.add(task.id); else n.delete(task.id); return n; })} />
                      </TableCell>
                    )}
                    <TableCell className="max-w-md whitespace-normal">{task.title}{task.is_custom && <span className="ml-2 rounded border border-primary/40 px-1 text-[10px] text-primary">{t("responsibilities.new")}</span>}</TableCell>
                    <TableCell className="text-muted-foreground">{p ? <>{p.name}<div className="text-xs">{model.systemName(p)}</div></> : "—"}</TableCell>
                    <TableCell>
                      {can.edit ? (
                        <Select value={fromId(task.owner)} onValueChange={(v) => changeOwner(task, v)}>
                          <SelectTrigger size="sm" className="w-full"><SelectValue /></SelectTrigger>
                          <SelectContent>
                            <SelectItem value={NONE}>{t("common.unassigned")}</SelectItem>
                            {model.memberOrder.map((mm) => <SelectItem key={mm.id} value={String(mm.id)}>{mm.name}</SelectItem>)}
                          </SelectContent>
                        </Select>
                      ) : (
                        <span className="flex items-center gap-2"><MemberAvatar member={m} size={22} />{m?.name ?? t("common.unassigned")}</span>
                      )}
                      {task.fallbacks.length > 0 && (
                        <button type="button" onClick={() => can.edit && setEdit(task)} className="mt-1 flex flex-wrap items-center gap-1 text-left text-xs text-muted-foreground" title={t("forms.task.fallbacksHint")}>
                          {task.fallbacks.map((f, i) => (
                            <span key={f.member} className="inline-flex items-center gap-1" title={f.condition || undefined}>
                              <span className="text-primary">→</span>
                              <span className="font-mono text-[10px]">{i + 2}.</span>
                              {model.member.get(f.member)?.name ?? "?"}
                            </span>
                          ))}
                        </button>
                      )}
                    </TableCell>
                    <TableCell>
                      {can.edit
                        ? <Button variant="ghost" size="icon" className="size-8" onClick={() => setEdit(task)} aria-label={t("common.edit")}><Pencil className="size-4" /></Button>
                        : <Button variant="ghost" size="icon" className="size-8" onClick={() => setPropose(task)} title={t("approvals.propose")}><GitPullRequestArrow className="size-4" /></Button>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Card>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-3">
          {columns.map(({ id, member }) => {
            const tasks = visible.filter((x) => (x.owner ?? null) === id);
            return (
              <div
                key={id ?? "none"}
                onDragOver={(e) => { if (dragging !== null) { e.preventDefault(); setOver(id ?? -1); } }}
                onDragLeave={() => setOver(null)}
                onDrop={(e) => {
                  e.preventDefault();
                  const task = dragging !== null ? model.task.get(dragging) : undefined;
                  setDragging(null);
                  setOver(null);
                  if (!task || (task.owner ?? null) === id) return;
                  if (can.edit) move.mutate({ id: task.id, to: id });
                  else setPropose({ ...task, owner: id });
                }}
                className={cn("flex max-h-[calc(100vh-260px)] w-72 shrink-0 flex-col rounded-xl border bg-card", over === (id ?? -1) && "border-primary bg-primary/5")}
              >
                <div className="flex items-center gap-2.5 border-b px-3 py-2.5">
                  <MemberAvatar member={member} size={28} />
                  <div className="min-w-0 flex-1"><div className="truncate text-sm font-semibold">{member?.name ?? t("common.unassigned")}</div>
                    <div className="truncate text-xs text-muted-foreground">{member?.role ?? t("responsibilities.noOwner")}</div></div>
                  <span className="font-mono text-xs text-muted-foreground">{tasks.length}</span>
                </div>
                <div className="flex-1 space-y-1.5 overflow-y-auto p-2">
                  {tasks.map((task) => (
                    <div
                      key={task.id}
                      draggable
                      onDragStart={() => setDragging(task.id)}
                      onDragEnd={() => { setDragging(null); setOver(null); }}
                      onClick={() => can.edit && setEdit(task)}
                      className={cn("cursor-grab rounded-lg border bg-background p-2.5 text-[13px] hover:border-foreground/25", dragging === task.id && "opacity-40")}
                    >
                      {task.title}
                      <div className="mt-1 truncate text-[11px] text-muted-foreground">{task.process ? model.process.get(task.process)?.name : "—"}</div>
                    </div>
                  ))}
                  {!tasks.length && <p className="p-4 text-center text-xs text-muted-foreground">{t("responsibilities.dropHere")}</p>}
                </div>
              </div>
            );
          })}
        </div>
      )}
      <TaskDialog open={edit !== undefined} onOpenChange={(o) => !o && setEdit(undefined)} task={edit ?? undefined} />
      <ProposeDialog
        open={propose !== null}
        onOpenChange={(o) => !o && setPropose(null)}
        preset={proposePreset}
      />
    </Page>
  );
}
