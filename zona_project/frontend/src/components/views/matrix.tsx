"use client";

import Link from "next/link";
import { useTranslations } from "next-intl";
import { Fragment, useState } from "react";

import { Page, PageHeader } from "@/components/common/page";
import { RoleGlyph } from "@/components/common/role";
import { RolesDialog } from "@/components/forms/roles-dialog";
import { Card } from "@/components/ui/card";
import { useCan, useModel, useScope } from "@/hooks/use-org";
import type { Process } from "@/lib/api/types";
import { PROCESS_ROLES, ROLE_ORDER } from "@/lib/model";
import { cn } from "@/lib/utils";

/** Mas'uliyat matritsasi (RACI uslubi): jarayon × xodim. Katak — rollar; bosilsa tahrirlanadi yoki taklif qilinadi. */
export function Matrix() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const { scope, processInScope } = useScope();
  const [cell, setCell] = useState<{ p: number; m: number } | null>(null);
  const depts = [...model.state.departments.map((d) => d.id), 0].filter((d) => model.membersOf(d).length && (!scope || d === scope));
  const cols = depts.flatMap((d) => model.membersOf(d));
  const groups = new Map<string, Process[]>();
  for (const p of model.state.processes) {
    if (!processInScope(p.id)) continue;
    const key = model.systemName(p) || t("org.noSystem");
    groups.set(key, [...(groups.get(key) ?? []), p]);
  }

  return (
    <Page>
      <PageHeader title={t("nav.matrix")} description={can.edit ? t("matrix.descriptionEdit") : t("matrix.descriptionView")} />
      <div className="mb-3 flex flex-wrap gap-4 text-xs text-muted-foreground">
        {ROLE_ORDER.map((r) => (
          <span key={r} className="flex items-center gap-1.5">
            {r === "executor" ? <span className="font-mono">12</span> : <RoleGlyph role={r} />}{t(`roles.${r}`)}
          </span>
        ))}
      </div>
      <Card className="gap-0 overflow-auto p-0">
        <table className="w-full border-separate border-spacing-0 text-[13px]">
          <thead>
            <tr>
              <th className="sticky left-0 top-0 z-20 bg-elevated" />
              {depts.map((d) => (
                <th key={d} colSpan={model.membersOf(d).length} className="sticky top-0 z-10 border-b border-l bg-elevated px-2 py-2 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">
                  {model.dept.get(d)?.name ?? t("org.noDepartment")}
                </th>
              ))}
            </tr>
            <tr>
              <th className="sticky left-0 top-[33px] z-20 min-w-72 border-b bg-elevated px-3 py-2 text-left text-xs font-medium text-muted-foreground">{t("processes.process")}</th>
              {cols.map((m) => (
                <th key={m.id} className="sticky top-[33px] z-10 min-w-28 border-b border-l bg-elevated px-2 py-2 text-center text-xs font-medium">
                  <Link href={`/employees/${m.id}`} className="hover:text-primary">{m.name}</Link>
                  <div className="truncate text-[10.5px] font-normal text-muted-foreground">{m.role}</div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {[...groups.entries()].map(([g, list]) => (
              <Fragment key={g}>
                <tr><td colSpan={cols.length + 1} className="bg-background px-3 pb-1.5 pt-4 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">{g}</td></tr>
                {list.map((p) => {
                  const level = model.level(p.id);
                  return (
                    <tr key={p.id} className="group">
                      <td className="sticky left-0 z-10 border-b bg-card px-3 py-2 group-hover:bg-muted">
                        <Link href={`/organization?focus=process:${p.id}`} className="flex items-center gap-2 hover:text-primary">
                          {level && <span className={cn("size-1.5 shrink-0 rounded-full", level === "danger" ? "bg-destructive" : "bg-warning")} />}
                          <span className="truncate font-medium">{p.name}</span>
                        </Link>
                        <div className="text-[11px] text-muted-foreground">{t("org.tasks", { count: (model.tasksOf.get(p.id) ?? []).length })}</div>
                      </td>
                      {cols.map((m) => {
                        const l = model.link(p.id, m.id);
                        return (
                          <td
                            key={m.id}
                            onClick={() => setCell({ p: p.id, m: m.id })}
                            className="cursor-pointer border-b border-l text-center hover:bg-primary/10 group-hover:bg-muted/50"
                          >
                            <span className="inline-flex flex-wrap justify-center gap-0.5">
                              {l && PROCESS_ROLES.filter((r) => l.roles.has(r)).map((r) => <RoleGlyph key={r} role={r} />)}
                              {l && l.tasks > 0 && <span className="px-1 font-mono text-[11px] text-muted-foreground">{l.tasks}</span>}
                            </span>
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </Fragment>
            ))}
          </tbody>
        </table>
      </Card>
      {cell && <RolesDialog open onOpenChange={(o) => !o && setCell(null)} processId={cell.p} memberId={cell.m} />}
    </Page>
  );
}
