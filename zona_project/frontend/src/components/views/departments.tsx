"use client";

import { Building2, Network, Pencil, Plus, Users } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { Page, PageHeader } from "@/components/common/page";
import { MemberDialog } from "@/components/forms/member-dialog";
import { DepartmentDialog, TeamDialog } from "@/components/forms/structure-dialogs";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useCan, useModel } from "@/hooks/use-org";
import type { Department, Team } from "@/lib/api/types";

/** Bo'limlar va jamoalar: tuzilma, a'zolar, egalik qilgan jarayonlar, muammolar. */
export function Departments() {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const [dept, setDept] = useState<Department | null | undefined>(undefined);
  const [team, setTeam] = useState<{ team?: Team; department?: number } | undefined>(undefined);
  const [member, setMember] = useState<number | null | undefined>(undefined);

  return (
    <Page>
      <PageHeader
        title={t("nav.departments")}
        description={t("departments.description")}
        actions={can.edit && <Button onClick={() => setDept(null)}><Plus className="size-4" />{t("forms.dept.new")}</Button>}
      />
      <div className="grid gap-4 xl:grid-cols-2">
        {model.state.departments.map((d) => {
          const members = model.membersOf(d.id);
          const owned = new Set(members.flatMap((m) => (model.linksOfMember.get(m.id) ?? []).filter((l) => l.roles.has("owner")).map((l) => l.processId)));
          const issues = [...owned].filter((pid) => (model.issues.get(pid) ?? []).length).length;
          const noBackup = [...owned].filter((pid) => !model.hasRole(pid, "backup")).length;
          const teams = model.teamsOf(d.id);
          const loose = model.membersOfTeam(null, d.id);
          return (
            <Card key={d.id} className="gap-4 p-5">
              <div className="flex items-start gap-3">
                <span className="grid size-11 place-items-center rounded-xl border bg-primary/10 text-primary"><Building2 className="size-5" /></span>
                <div className="min-w-0 flex-1">
                  <h2 className="font-semibold">{d.name}</h2>
                  <p className="text-sm text-muted-foreground">{d.description}</p>
                </div>
                <Button asChild variant="ghost" size="icon"><Link href={`/organization?focus=dept:${d.id}`} aria-label={t("overview.openMap")}><Network className="size-4" /></Link></Button>
                {can.edit && <Button variant="ghost" size="icon" onClick={() => setDept(d)} aria-label={t("common.edit")}><Pencil className="size-4" /></Button>}
              </div>
              <div className="grid grid-cols-4 gap-2 text-center">
                {([[t("org.employees"), members.length], [t("org.teams"), teams.length], [t("panel.owned"), owned.size], [t("panel.tasks"), members.reduce((s, m) => s + (model.load.get(m.id) ?? 0), 0)]] as const).map(([l, v]) => (
                  <div key={l} className="rounded-lg bg-muted/50 py-2"><div className="font-mono text-lg font-semibold">{v}</div><div className="text-[11px] text-muted-foreground">{l}</div></div>
                ))}
              </div>
              <div className="flex flex-wrap gap-2">
                {issues ? <Badge variant="outline" className="border-warning/50 text-warning">{t("departments.issues", { count: issues })}</Badge>
                  : <Badge variant="outline" className="border-success/50 text-success">{t("departments.clear")}</Badge>}
                {owned.size > 0 && <Badge variant="outline">{t("departments.noBackup", { count: noBackup })}</Badge>}
              </div>
              <div className="grid gap-2">
                {teams.map((tm) => {
                  const tms = model.membersOfTeam(tm.id, d.id);
                  const lead = tm.lead ? model.member.get(tm.lead) : undefined;
                  return (
                    <div key={tm.id} className="rounded-xl border bg-muted/20 p-3">
                      <div className="mb-2 flex items-center gap-2 text-sm">
                        <Users className="size-4 text-muted-foreground" /><b className="font-medium">{tm.name}</b>
                        {lead && <span className="text-xs text-muted-foreground">· {t("org.lead", { name: lead.name })}</span>}
                        {can.edit && <Button variant="ghost" size="icon" className="ml-auto size-7" onClick={() => setTeam({ team: tm })}><Pencil className="size-3.5" /></Button>}
                      </div>
                      <div className="flex flex-wrap gap-1.5">
                        {tms.map((m) => (
                          <Link key={m.id} href={`/employees/${m.id}`} className="flex items-center gap-1.5 rounded-full border bg-card py-0.5 pl-0.5 pr-2.5 text-xs hover:border-primary/40">
                            <MemberAvatar member={m} size={22} />{m.name}
                          </Link>
                        ))}
                        {!tms.length && <span className="text-xs text-muted-foreground">{t("departments.emptyTeam")}</span>}
                      </div>
                    </div>
                  );
                })}
                {loose.length > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {loose.map((m) => (
                      <Link key={m.id} href={`/employees/${m.id}`} className="flex items-center gap-1.5 rounded-full border bg-card py-0.5 pl-0.5 pr-2.5 text-xs hover:border-primary/40">
                        <MemberAvatar member={m} size={22} />{m.name}
                      </Link>
                    ))}
                  </div>
                )}
              </div>
              {can.edit && (
                <div className="flex gap-2">
                  <Button size="sm" variant="outline" onClick={() => setTeam({ department: d.id })}><Plus className="size-4" />{t("forms.team.new")}</Button>
                  <Button size="sm" variant="outline" onClick={() => setMember(d.id)}><Plus className="size-4" />{t("forms.member.new")}</Button>
                </div>
              )}
            </Card>
          );
        })}
      </div>
      <DepartmentDialog open={dept !== undefined} onOpenChange={(o) => !o && setDept(undefined)} department={dept ?? undefined} />
      <TeamDialog open={team !== undefined} onOpenChange={(o) => !o && setTeam(undefined)} team={team?.team} presetDepartment={team?.department} />
      <MemberDialog open={member !== undefined} onOpenChange={(o) => !o && setMember(undefined)} presetDepartment={member ?? undefined} />
    </Page>
  );
}
