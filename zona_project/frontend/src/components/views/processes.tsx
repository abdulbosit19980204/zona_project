"use client";

import { AlertTriangle, Pencil, Plus, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useTranslations } from "next-intl";
import { Fragment, useMemo, useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Page, PageHeader } from "@/components/common/page";
import { ProcessDialog } from "@/components/forms/structure-dialogs";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCan, useModel, useScope } from "@/hooks/use-org";
import type { Process, ProcessRoleKey } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const norm = (s: string) => s.toLowerCase().replace(/[ʻʼ’‘`´]/g, "'");

/** Biznes jarayonlar: egasi, ijrochilari, tasdiqlovchi/nazoratchi, zaxira va muammolar. */
export function Processes() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const router = useRouter();
  const { processInScope } = useScope();
  const [query, setQuery] = useState("");
  const [onlyIssues, setOnlyIssues] = useState(false);
  const [edit, setEdit] = useState<Process | null | undefined>(undefined);

  const groups = useMemo(() => {
    const q = norm(query.trim());
    const map = new Map<string, Process[]>();
    for (const p of model.state.processes) {
      if (!processInScope(p.id)) continue;
      if (onlyIssues && !(model.issues.get(p.id) ?? []).length) continue;
      if (q && !norm(`${p.name} ${model.systemName(p)} ${p.description}`).includes(q)) continue;
      const key = model.systemName(p) || t("org.noSystem");
      map.set(key, [...(map.get(key) ?? []), p]);
    }
    return [...map.entries()];
  }, [model, query, onlyIssues, processInScope, t]);

  const people = (pid: number, role: ProcessRoleKey) =>
    (model.rolesOf.get(pid) ?? []).filter((r) => r.role === role).map((r) => model.member.get(r.member)).filter((m) => m !== undefined);

  return (
    <Page>
      <PageHeader
        title={t("nav.processes")}
        description={t("processes.description")}
        actions={can.edit && <Button onClick={() => setEdit(null)}><Plus className="size-4" />{t("forms.process.new")}</Button>}
      />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-72"><Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("processes.filter")} className="pl-8" /></div>
        <Button variant={onlyIssues ? "default" : "outline"} onClick={() => setOnlyIssues((v) => !v)}>
          <AlertTriangle className="size-4" />{t("org.onlyIssues")} · {model.issueProcesses.length}
        </Button>
      </div>
      <Card className="gap-0 overflow-hidden p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-6" />
              <TableHead>{t("processes.process")}</TableHead>
              <TableHead>{t("roles.owner")}</TableHead>
              <TableHead>{t("processes.executors")}</TableHead>
              <TableHead>{t("processes.control")}</TableHead>
              <TableHead>{t("roles.backup")}</TableHead>
              <TableHead className="text-right">{t("panel.tasks")}</TableHead>
              <TableHead className="w-12" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {groups.map(([group, list]) => (
              <Fragment key={group}>
                <TableRow className="bg-muted/40 hover:bg-muted/40">
                  <TableCell colSpan={8} className="py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{group} · {list.length}</TableCell>
                </TableRow>
                {list.map((p) => {
                  const level = model.level(p.id);
                  const owners = people(p.id, "owner");
                  const control = [...people(p.id, "approver"), ...people(p.id, "supervisor")];
                  const backup = people(p.id, "backup");
                  const execs = [...(model.linksOfProcess.get(p.id) ?? [])].filter((l) => l.roles.has("executor")).sort((a, b) => b.tasks - a.tasks);
                  const chip = (id: number, name: string, extra?: string) => (
                    <span key={`${id}${extra ?? ""}`} className="inline-flex items-center gap-1.5 rounded-full border bg-muted/40 py-0.5 pl-0.5 pr-2 text-xs">
                      <MemberAvatar member={model.member.get(id)} size={20} />{name}{extra && <span className="text-muted-foreground">· {extra}</span>}
                    </span>
                  );
                  return (
                    <TableRow key={p.id} className="cursor-pointer" onClick={() => router.push(`/organization?focus=process:${p.id}`)}>
                      <TableCell>{level && <span className={cn("block size-2 rounded-full", level === "danger" ? "bg-destructive" : "bg-warning")} title={(model.issues.get(p.id) ?? []).map((i) => t(`issues.${i.code}`, { count: i.count ?? 0 })).join(", ")} />}</TableCell>
                      <TableCell className="max-w-xs whitespace-normal font-medium">{p.name}</TableCell>
                      <TableCell><div className="flex flex-wrap gap-1">{owners.map((m) => chip(m.id, m.name))}{!owners.length && <span className="rounded-md border border-destructive/40 px-1.5 text-xs text-destructive">{t("org.noOwner")}</span>}</div></TableCell>
                      <TableCell><div className="flex flex-wrap gap-1">{execs.map((l) => chip(l.memberId, model.member.get(l.memberId)?.name ?? "", String(l.tasks)))}</div></TableCell>
                      <TableCell><div className="flex flex-wrap gap-1">{control.map((m) => chip(m.id, m.name))}{!control.length && <span className="text-xs text-muted-foreground">—</span>}</div></TableCell>
                      <TableCell><div className="flex flex-wrap gap-1">{backup.map((m) => chip(m.id, m.name))}{!backup.length && <span className="text-xs text-muted-foreground">{t("processes.noBackup")}</span>}</div></TableCell>
                      <TableCell className="text-right font-mono">{(model.tasksOf.get(p.id) ?? []).length}</TableCell>
                      <TableCell>{can.edit && <Button variant="ghost" size="icon" className="size-8" onClick={(e) => { e.stopPropagation(); setEdit(p); }}><Pencil className="size-4" /></Button>}</TableCell>
                    </TableRow>
                  );
                })}
              </Fragment>
            ))}
          </TableBody>
        </Table>
      </Card>
      <ProcessDialog open={edit !== undefined} onOpenChange={(o) => !o && setEdit(undefined)} process={edit ?? undefined} />
    </Page>
  );
}
