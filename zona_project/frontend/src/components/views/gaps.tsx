"use client";

import { CheckCircle2, CircleSlash, Copy, ShieldOff, Split, UserX, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Page, PageHeader } from "@/components/common/page";
import { TaskDialog } from "@/components/forms/task-dialog";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { useCan, useModel, useScope } from "@/hooks/use-org";
import type { Process, Task } from "@/lib/api/types";
import { cn } from "@/lib/utils";

/** Javobgarlik bo'shliqlari: egasiz, ko'p egali, nazoratsiz, zaxirasiz jarayonlar va mas'ulsiz vazifalar. */
export function Gaps() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const { processInScope } = useScope();
  const [task, setTask] = useState<Task | undefined>(undefined);
  const ps = model.state.processes.filter((p) => processInScope(p.id));
  const has = (code: string) => (p: Process) => (model.issues.get(p.id) ?? []).some((i) => i.code === code);

  const groups: { key: string; icon: typeof UserX; danger?: boolean; items: Process[] }[] = [
    { key: "noOwner", icon: UserX, danger: true, items: ps.filter(has("no_owner")) },
    { key: "multiOwner", icon: Copy, items: ps.filter(has("multi_owner")) },
    { key: "noControl", icon: ShieldOff, items: ps.filter((p) => !model.hasRole(p.id, "approver") && !model.hasRole(p.id, "supervisor")) },
    { key: "noBackup", icon: Users, items: ps.filter((p) => !model.hasRole(p.id, "backup")) },
    { key: "splitExec", icon: Split, items: ps.filter(has("split_exec")) },
    { key: "empty", icon: CircleSlash, items: ps.filter(has("empty")) },
  ];
  const unassigned = model.unassignedTasks;
  const orphans = model.orphanTasks.filter((x) => x.owner);

  return (
    <Page>
      <PageHeader title={t("nav.gaps")} description={t("gaps.description")} />
      <div className="mb-4 grid gap-3 sm:grid-cols-3 xl:grid-cols-6">
        {groups.map((g) => (
          <a key={g.key} href={`#${g.key}`} className="rounded-xl border bg-card px-4 py-3 hover:border-primary/40">
            <div className="flex items-center gap-2 text-xs text-muted-foreground"><g.icon className="size-3.5" />{t(`gaps.${g.key}`)}</div>
            <div className={cn("mt-1 font-mono text-2xl font-semibold", g.items.length && (g.danger ? "text-destructive" : "text-warning"))}>{g.items.length}</div>
          </a>
        ))}
      </div>
      <div className="grid gap-4 xl:grid-cols-2">
        {groups.map((g) => (
          <Section key={g.key} id={g.key} icon={g.icon} title={t(`gaps.${g.key}`)} hint={t(`gaps.${g.key}Hint`)} count={g.items.length}>
            {g.items.map((p) => {
              const owner = model.primaryOwner.get(p.id);
              const m = owner ? model.member.get(owner) : undefined;
              return (
                <Link key={p.id} href={`/organization?focus=process:${p.id}`} className="flex items-center gap-3 rounded-lg px-2 py-2 text-sm hover:bg-muted/60">
                  <span className={cn("size-1.5 rounded-full", model.level(p.id) === "danger" ? "bg-destructive" : "bg-warning")} />
                  <span className="min-w-0 flex-1 truncate">{p.name}<span className="ml-2 text-xs text-muted-foreground">{model.systemName(p)}</span></span>
                  {m && <span className="flex items-center gap-1.5 text-xs text-muted-foreground"><MemberAvatar member={m} size={18} />{m.name}</span>}
                </Link>
              );
            })}
          </Section>
        ))}
        <Section id="unassigned" icon={UserX} title={t("gaps.unassigned")} hint={t("gaps.unassignedHint")} count={unassigned.length}>
          {unassigned.map((x) => (
            <button key={x.id} type="button" disabled={!can.edit} onClick={() => setTask(x)} className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-sm enabled:hover:bg-muted/60">
              <span className="size-1.5 rounded-full bg-destructive" />
              <span className="min-w-0 flex-1 truncate">{x.title}</span>
              <span className="truncate text-xs text-muted-foreground">{x.process ? model.process.get(x.process)?.name : "—"}</span>
            </button>
          ))}
        </Section>
        <Section id="orphans" icon={CircleSlash} title={t("gaps.orphans")} hint={t("gaps.orphansHint")} count={orphans.length}>
          {orphans.map((x) => (
            <button key={x.id} type="button" disabled={!can.edit} onClick={() => setTask(x)} className="flex w-full items-center gap-3 rounded-lg px-2 py-2 text-left text-sm enabled:hover:bg-muted/60">
              <span className="size-1.5 rounded-full bg-warning" />
              <span className="min-w-0 flex-1 truncate">{x.title}</span>
              <span className="truncate text-xs text-muted-foreground">{x.owner ? model.member.get(x.owner)?.name : ""}</span>
            </button>
          ))}
        </Section>
      </div>
      <TaskDialog open={task !== undefined} onOpenChange={(o) => !o && setTask(undefined)} task={task} />
    </Page>
  );
}

function Section({ id, icon: Icon, title, hint, count, children }: {
  id: string; icon: typeof UserX; title: string; hint: string; count: number; children: ReactNode;
}) {
  const t = useTranslations("gaps");
  return (
    <Card id={id} className="scroll-mt-4 gap-2 p-4">
      <div className="flex items-start gap-3">
        <span className="grid size-8 place-items-center rounded-lg border"><Icon className="size-4 text-muted-foreground" /></span>
        <div className="min-w-0 flex-1">
          <div className="text-sm font-semibold">{title}</div>
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
        <Badge variant="outline" className="font-mono">{count}</Badge>
      </div>
      <div className="max-h-80 overflow-y-auto">
        {count ? children : <p className="flex items-center gap-2 px-2 py-3 text-sm text-success"><CheckCircle2 className="size-4" />{t("none")}</p>}
      </div>
    </Card>
  );
}
