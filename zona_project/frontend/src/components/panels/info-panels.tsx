"use client";

import { ArrowRight, Building2, GitPullRequestArrow, Layers, Orbit, Pencil, Plus, Users, X } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";
import { useState, type ReactNode } from "react";

import { ContactLinks } from "@/components/common/contacts";
import { MemberAvatar } from "@/components/common/member-avatar";
import { RoleGlyph, RoleLegend } from "@/components/common/role";
import { MemberDialog } from "@/components/forms/member-dialog";
import { ProposeDialog } from "@/components/forms/propose-dialog";
import { DepartmentDialog, ProcessDialog } from "@/components/forms/structure-dialogs";
import { TaskDialog } from "@/components/forms/task-dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { useCan, useModel, useOrgMutation } from "@/hooks/use-org";
import { approvalsApi, orgApi } from "@/lib/api/endpoints";
import type { ProcessRoleKey, Task } from "@/lib/api/types";
import { PROCESS_ROLES, ROLE_ORDER, type Link as RoleLink } from "@/lib/model";
import { cn } from "@/lib/utils";

export function PanelSection({ title, count, children, className }: { title: string; count?: number; children: ReactNode; className?: string }) {
  return (
    <section className={cn("border-b px-5 py-4", className)}>
      <h3 className="mb-2.5 flex items-center text-[10.5px] font-semibold uppercase tracking-[0.12em] text-muted-foreground">
        {title}{count !== undefined && <span className="ml-auto font-mono tracking-normal">{count}</span>}
      </h3>
      {children}
    </section>
  );
}

function Row({ onClick, href, children }: { onClick?: () => void; href?: string; children: ReactNode }) {
  const cls = "-mx-2 flex w-[calc(100%+1rem)] items-center gap-2.5 rounded-lg px-2 py-1.5 text-left text-[13px] hover:bg-muted";
  if (href) return <Link href={href} className={cls}>{children}</Link>;
  return <button type="button" onClick={onClick} className={cls}>{children}</button>;
}

function Stats({ items }: { items: [string, ReactNode][] }) {
  return (
    <div className="grid grid-cols-3 gap-2">
      {items.map(([label, value]) => (
        <div key={label} className="rounded-lg border bg-muted/40 px-3 py-2">
          <div className="font-mono text-lg font-semibold">{value}</div>
          <div className="text-[11px] text-muted-foreground">{label}</div>
        </div>
      ))}
    </div>
  );
}

/* ================================================================== xodim */
export function EmployeePanel({ memberId, onSelect }: { memberId: number; onSelect: (key: string) => void }) {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const [edit, setEdit] = useState(false);
  const [newTask, setNewTask] = useState(false);
  const [propose, setPropose] = useState(false);
  const m = model.member.get(memberId);
  if (!m) return null;
  const links = [...(model.linksOfMember.get(m.id) ?? [])].sort((a, b) => ROLE_ORDER.indexOf(a.top) - ROLE_ORDER.indexOf(b.top) || b.tasks - a.tasks);
  const primary = links.filter((l) => l.roles.has("owner") || l.roles.has("executor"));
  const secondary = links.filter((l) => !l.roles.has("owner") && !l.roles.has("executor"));
  const approvals = links.filter((l) => l.roles.has("approver"));
  const authorities = model.authorities.get(m.id) ?? [];
  const dept = m.department ? model.dept.get(m.department) : undefined;
  const team = m.team ? model.team.get(m.team) : undefined;
  const manager = m.manager ? model.member.get(m.manager) : undefined;
  const reports = model.reports.get(m.id) ?? [];
  const peers = [...model.peers(m.id).entries()].sort((a, b) => b[1] - a[1]);
  const processRow = (l: RoleLink) => {
    const p = model.process.get(l.processId)!;
    return (
      <Row key={l.processId} onClick={() => onSelect(`process:${p.id}`)}>
        <span className="flex shrink-0 gap-0.5">{ROLE_ORDER.filter((r) => l.roles.has(r)).map((r) => <RoleGlyph key={r} role={r} />)}</span>
        <span className="min-w-0 flex-1 truncate">{p.name}</span>
        {l.tasks > 0 && <span className="font-mono text-[11px] text-muted-foreground">{l.tasks}</span>}
      </Row>
    );
  };
  return (
    <>
      <div className="flex items-start gap-3 border-b px-5 py-5">
        <MemberAvatar member={m} size={48} />
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold leading-tight">{m.name}</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{m.role}</p>
        </div>
        {can.edit && <Button size="icon" variant="ghost" onClick={() => setEdit(true)} aria-label={t("common.edit")}><Pencil className="size-4" /></Button>}
      </div>
      <PanelSection title={t("panel.overview")}>
        <Stats items={[[t("panel.tasks"), model.load.get(m.id) ?? 0], [t("panel.owned"), links.filter((l) => l.roles.has("owner")).length], [t("panel.authority"), approvals.length + authorities.length]]} />
        <Button asChild size="sm" className="mt-3 w-full"><Link href={`/employees/${m.id}`}><Orbit className="size-4" />{t("panel.open360")}</Link></Button>
      </PanelSection>
      <PanelSection title={t("panel.profile")}>
        <dl className="grid grid-cols-[110px_1fr] gap-x-3 gap-y-2 text-[13px]">
          <dt className="text-muted-foreground">{t("forms.department")}</dt>
          <dd>{dept ? <button className="hover:underline" onClick={() => onSelect(`dept:${dept.id}`)}>{dept.name}</button> : "—"}</dd>
          <dt className="text-muted-foreground">{t("forms.teamField")}</dt><dd>{team?.name ?? "—"}</dd>
          <dt className="text-muted-foreground">{t("forms.member.manager")}</dt>
          <dd>{manager ? <button className="hover:underline" onClick={() => onSelect(`member:${manager.id}`)}>{manager.name}</button> : "—"}</dd>
          {reports.length > 0 && (<><dt className="text-muted-foreground">{t("panel.reports")}</dt><dd>{reports.map((r) => r.name).join(", ")}</dd></>)}
        </dl>
        <div className="mt-3"><ContactLinks contact={m} empty={t("panel.noContacts")} /></div>
      </PanelSection>
      <PanelSection title={t("panel.primary")} count={primary.length}>
        {primary.map(processRow)}
        {!primary.length && <p className="text-sm text-muted-foreground">{t("panel.none")}</p>}
      </PanelSection>
      {secondary.length > 0 && <PanelSection title={t("panel.secondary")} count={secondary.length}>{secondary.map(processRow)}</PanelSection>}
      <PanelSection title={t("panel.approvalAuthority")} count={approvals.length + authorities.length}>
        {authorities.map((a) => (
          <div key={a.id} className="mb-1.5 rounded-lg border border-dashed border-violet/50 px-3 py-2 text-[13px]">
            <div className="font-medium">{a.title}</div>
            {a.scope && <div className="text-xs text-muted-foreground">{a.scope}</div>}
          </div>
        ))}
        {approvals.map(processRow)}
        {!approvals.length && !authorities.length && <p className="text-sm text-muted-foreground">{t("panel.none")}</p>}
      </PanelSection>
      {(m.does || m.excludes) && (
        <PanelSection title={t("panel.boundaries")}>
          {m.does && <p className="text-[13px]">{m.does}</p>}
          {m.excludes && <p className="mt-2 text-[13px] text-muted-foreground"><b className="text-foreground">{t("panel.notResponsible")}:</b> {m.excludes}</p>}
        </PanelSection>
      )}
      {peers.length > 0 && (
        <PanelSection title={t("panel.connected")} count={peers.length}>
          {peers.map(([id, n]) => {
            const p = model.member.get(id);
            return p ? (
              <Row key={id} onClick={() => onSelect(`member:${id}`)}>
                <MemberAvatar member={p} size={24} /><span className="min-w-0 flex-1 truncate">{p.name}</span>
                <span className="text-[11px] text-muted-foreground">{t("panel.shared", { count: n })}</span>
              </Row>
            ) : null;
          })}
        </PanelSection>
      )}
      <div className="flex flex-wrap gap-2 px-5 py-4">
        {can.edit && <Button size="sm" variant="outline" onClick={() => setNewTask(true)}><Plus className="size-4" />{t("forms.task.new")}</Button>}
        <Button size="sm" variant="outline" onClick={() => setPropose(true)}><GitPullRequestArrow className="size-4" />{t("approvals.propose")}</Button>
      </div>
      <MemberDialog open={edit} onOpenChange={setEdit} member={m} />
      <TaskDialog open={newTask} onOpenChange={setNewTask} preset={{ owner: m.id }} />
      <ProposeDialog open={propose} onOpenChange={setPropose} preset={{ kind: "role_add", member: String(m.id) }} />
    </>
  );
}

/* ================================================================== jarayon */
export function ProcessPanel({ processId, onSelect }: { processId: number; onSelect: (key: string) => void }) {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const [edit, setEdit] = useState(false);
  const [task, setTask] = useState<Task | null | undefined>(undefined);
  const [addMember, setAddMember] = useState<string>("");
  const [addRole, setAddRole] = useState<ProcessRoleKey | "executor">("backup");
  const p = model.process.get(processId);
  const removeRole = useOrgMutation((id: number) => (can.edit ? orgApi.roles.remove(id) : approvalsApi.create("role_remove", { role_id: id }, "").then(() => undefined)),
    can.edit ? t("forms.roles.saved") : t("forms.roles.proposed"));
  const add = useOrgMutation(async (): Promise<unknown> => {
    // ijrochi jarayon roli emas: u vazifalar orqali beriladi (har bir vazifaga navbat bilan)
    if (addRole === "executor") return orgApi.tasks.processExecutor(processId, Number(addMember));
    const body = { process: processId, member: Number(addMember), role: addRole };
    return can.edit ? orgApi.roles.create(body) : approvalsApi.create("role_add", body, "");
  }, can.edit ? t("forms.roles.saved") : t("forms.roles.proposed"));
  const removeExecutor = useOrgMutation((member: number) => orgApi.tasks.processExecutor(processId, member, true), t("forms.roles.saved"));
  if (!p) return null;
  const links = model.linksOfProcess.get(p.id) ?? [];
  const tasks = model.tasksOf.get(p.id) ?? [];
  const issues = model.issues.get(p.id) ?? [];
  return (
    <>
      <div className="flex items-start gap-3 border-b px-5 py-5">
        <span className="grid size-12 shrink-0 place-items-center rounded-xl border bg-primary/10 text-primary"><Layers className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold leading-tight">{p.name}</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{model.systemName(p) || t("org.noSystem")} · {t("org.tasks", { count: tasks.length })}</p>
        </div>
        {can.edit && <Button size="icon" variant="ghost" onClick={() => setEdit(true)} aria-label={t("common.edit")}><Pencil className="size-4" /></Button>}
      </div>
      {issues.length > 0 && (
        <PanelSection title={t("panel.issues")}>
          {issues.map((i) => (
            <div key={i.code} className={cn("mb-1.5 flex items-center gap-2 rounded-lg border px-3 py-2 text-[13px]", i.level === "danger" ? "border-destructive/40" : "border-warning/40")}>
              <span className={cn("size-2 rounded-full", i.level === "danger" ? "bg-destructive" : "bg-warning")} />{t(`issues.${i.code}`, { count: i.count ?? 0 })}
            </div>
          ))}
        </PanelSection>
      )}
      {p.description && <PanelSection title={t("forms.description")}><p className="text-[13px]">{p.description}</p></PanelSection>}
      <PanelSection title={t("panel.whoIsResponsible")}>
        <div className="grid gap-3">
          {ROLE_ORDER.map((role) => {
            const who = role === "executor"
              ? links.filter((l) => l.roles.has("executor")).sort((a, b) => b.tasks - a.tasks).map((l) => ({ key: `e${l.memberId}`, member: l.memberId, extra: String(l.tasks), roleId: null as number | null }))
              : (model.rolesOf.get(p.id) ?? []).filter((r) => r.role === role).map((r) => ({ key: `r${r.id}`, member: r.member, extra: "", roleId: r.id as number | null }));
            return (
              <div key={role} className="grid grid-cols-[110px_1fr] items-start gap-2">
                <span className="flex items-center gap-2 pt-0.5 text-xs text-muted-foreground"><RoleGlyph role={role} />{t(`roles.${role}`)}</span>
                <div className="flex flex-wrap gap-1.5">
                  {who.map((w) => {
                    const mm = model.member.get(w.member);
                    return mm ? (
                      <span key={w.key} className="inline-flex h-7 items-center gap-1.5 rounded-full border bg-muted/50 pl-0.5 pr-1 text-xs">
                        <button className="flex items-center gap-1.5" onClick={() => onSelect(`member:${mm.id}`)}><MemberAvatar member={mm} size={22} />{mm.name}{w.extra && ` · ${w.extra}`}</button>
                        {w.roleId !== null && (
                          <button className="grid size-5 place-items-center rounded-full text-muted-foreground hover:text-destructive" onClick={() => removeRole.mutate(w.roleId!)} title={t("panel.removeRole")}>
                            <X className="size-3" />
                          </button>
                        )}
                        {w.roleId === null && can.edit && (
                          <button className="grid size-5 place-items-center rounded-full text-muted-foreground hover:text-destructive" onClick={() => removeExecutor.mutate(w.member)} title={t("panel.removeExecutor")}>
                            <X className="size-3" />
                          </button>
                        )}
                      </span>
                    ) : null;
                  })}
                  {!who.length && <span className={cn("rounded-full border border-dashed px-2.5 py-0.5 text-xs", role === "owner" ? "border-destructive/50 text-destructive" : "text-muted-foreground")}>{role === "owner" ? t("panel.notAssigned") : "—"}</span>}
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-4 grid grid-cols-[1fr_120px_auto] gap-1.5">
          <Select value={addMember} onValueChange={setAddMember}>
            <SelectTrigger size="sm" className="w-full"><SelectValue placeholder={t("nav.employees")} /></SelectTrigger>
            <SelectContent>{model.memberOrder.map((mm) => <SelectItem key={mm.id} value={String(mm.id)}>{mm.name}</SelectItem>)}</SelectContent>
          </Select>
          <Select value={addRole} onValueChange={(v) => setAddRole(v as ProcessRoleKey | "executor")}>
            <SelectTrigger size="sm" className="w-full"><SelectValue /></SelectTrigger>
            <SelectContent>
              {(can.edit ? ROLE_ORDER : PROCESS_ROLES).map((r) => <SelectItem key={r} value={r}>{t(`roles.${r}`)}</SelectItem>)}
            </SelectContent>
          </Select>
          <Button size="sm" disabled={!addMember || add.isPending} onClick={() => add.mutate(undefined)}>{can.edit ? t("common.add") : t("forms.roles.propose")}</Button>
        </div>
      </PanelSection>
      <PanelSection title={t("nav.responsibilities")} count={tasks.length}>
        {tasks.map((task) => (
          <Row key={task.id} onClick={() => (can.edit ? setTask(task) : undefined)}>
            <MemberAvatar member={task.owner ? model.member.get(task.owner) : null} size={22} />
            <span className="min-w-0 flex-1 truncate" title={task.title}>{task.title}</span>
            {task.fallbacks.length > 0 && (
              <span className="shrink-0 rounded-full bg-muted px-1.5 font-mono text-[10px] text-muted-foreground" title={task.fallbacks.map((f) => model.member.get(f.member)?.name).join(", ")}>
                +{task.fallbacks.length}
              </span>
            )}
          </Row>
        ))}
        {can.edit && <Button size="sm" variant="outline" className="mt-2" onClick={() => setTask(null)}><Plus className="size-4" />{t("forms.task.new")}</Button>}
      </PanelSection>
      <ProcessDialog open={edit} onOpenChange={setEdit} process={p} />
      <TaskDialog
        open={task !== undefined} onOpenChange={(o) => !o && setTask(undefined)} task={task ?? undefined}
        preset={{ process: p.id, owner: model.primaryOwner.get(p.id) ?? null }}
      />
    </>
  );
}

/* ================================================================== bo'lim */
export function DepartmentPanel({ deptId, onSelect }: { deptId: number; onSelect: (key: string) => void }) {
  const t = useTranslations();
  const model = useModel();
  const can = useCan();
  const [edit, setEdit] = useState(false);
  const dept = model.dept.get(deptId);
  const members = model.membersOf(deptId);
  const teams = model.teamsOf(deptId);
  const owned = new Set(members.flatMap((m) => (model.linksOfMember.get(m.id) ?? []).filter((l) => l.roles.has("owner")).map((l) => l.processId)));
  const groups: [string, typeof members][] = [
    ...teams.map((tm) => [tm.name, model.membersOfTeam(tm.id, deptId)] as [string, typeof members]),
    [t("forms.noTeam"), model.membersOfTeam(null, deptId)],
  ];
  return (
    <>
      <div className="flex items-start gap-3 border-b px-5 py-5">
        <span className="grid size-12 shrink-0 place-items-center rounded-xl border bg-primary/10 text-primary"><Building2 className="size-5" /></span>
        <div className="min-w-0 flex-1">
          <h2 className="text-base font-semibold leading-tight">{dept?.name ?? t("org.noDepartment")}</h2>
          <p className="mt-0.5 text-[13px] text-muted-foreground">{dept?.description}</p>
        </div>
        {can.edit && dept && <Button size="icon" variant="ghost" onClick={() => setEdit(true)} aria-label={t("common.edit")}><Pencil className="size-4" /></Button>}
      </div>
      <PanelSection title={t("panel.overview")}>
        <Stats items={[[t("org.employees"), members.length], [t("panel.owned"), owned.size], [t("panel.tasks"), members.reduce((s, m) => s + (model.load.get(m.id) ?? 0), 0)]]} />
      </PanelSection>
      {groups.filter(([, ms]) => ms.length).map(([name, ms]) => (
        <PanelSection key={name} title={name} count={ms.length}>
          {ms.map((m) => (
            <Row key={m.id} onClick={() => onSelect(`member:${m.id}`)}>
              <MemberAvatar member={m} size={24} /><span className="min-w-0 flex-1 truncate">{m.name}</span>
              <span className="font-mono text-[11px] text-muted-foreground">{model.load.get(m.id) ?? 0}</span>
            </Row>
          ))}
        </PanelSection>
      ))}
      {dept && <DepartmentDialog open={edit} onOpenChange={setEdit} department={dept} />}
    </>
  );
}

/* ================================================================== kompaniya */
export function CompanyPanel({ onSelect }: { onSelect: (key: string) => void }) {
  const t = useTranslations();
  const model = useModel();
  return (
    <>
      <div className="flex items-start gap-3 border-b px-5 py-5">
        <span className="grid size-12 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-primary to-violet font-bold text-white">{model.state.meta.company.slice(0, 2).toUpperCase()}</span>
        <div><h2 className="text-base font-semibold">{model.state.meta.company}</h2><p className="text-[13px] text-muted-foreground">{t("panel.selectHint")}</p></div>
      </div>
      <PanelSection title={t("panel.overview")}>
        <Stats items={[[t("org.employees"), model.state.members.length], [t("org.processes"), model.state.processes.length], [t("panel.tasks"), model.state.tasks.length]]} />
      </PanelSection>
      <PanelSection title={t("panel.attention")} count={model.issueProcesses.length}>
        {model.issueProcesses.slice(0, 8).map((p) => (
          <Row key={p.id} onClick={() => onSelect(`process:${p.id}`)}>
            <span className={cn("size-2 rounded-full", model.level(p.id) === "danger" ? "bg-destructive" : "bg-warning")} />
            <span className="min-w-0 flex-1 truncate">{p.name}</span><ArrowRight className="size-3.5 text-muted-foreground" />
          </Row>
        ))}
        {!model.issueProcesses.length && <p className="text-sm text-muted-foreground">{t("panel.allGood")}</p>}
      </PanelSection>
      <PanelSection title={t("panel.legend")}><RoleLegend /></PanelSection>
      <PanelSection title={t("org.teams")} count={model.state.teams.length} className="border-b-0">
        {model.state.teams.map((tm) => (
          <Row key={tm.id} onClick={() => onSelect(`dept:${tm.department}`)}>
            <Users className="size-4 text-muted-foreground" /><span className="min-w-0 flex-1 truncate">{tm.name}</span>
            <span className="text-[11px] text-muted-foreground">{model.dept.get(tm.department)?.name}</span>
          </Row>
        ))}
      </PanelSection>
    </>
  );
}

/** Tanlangan tugunga mos panel. key: "member:5" | "process:3" | "dept:2" | "team:1" | "company:0" */
export function InfoPanel({ selected, onSelect }: { selected: string | null; onSelect: (key: string) => void }) {
  const model = useModel();
  const [kind, raw] = (selected ?? "company:0").split(":");
  const id = Number(raw);
  if (kind === "member" && model.member.has(id)) return <EmployeePanel memberId={id} onSelect={onSelect} />;
  if (kind === "process" && model.process.has(id)) return <ProcessPanel processId={id} onSelect={onSelect} />;
  if (kind === "dept") return <DepartmentPanel deptId={id} onSelect={onSelect} />;
  if (kind === "team" && model.team.has(id)) return <DepartmentPanel deptId={model.team.get(id)!.department} onSelect={onSelect} />;
  return <CompanyPanel onSelect={onSelect} />;
}
