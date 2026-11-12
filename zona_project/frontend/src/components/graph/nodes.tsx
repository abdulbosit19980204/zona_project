"use client";

import { Handle, Position, type NodeProps } from "@xyflow/react";
import { Building2, ChevronDown, ChevronRight, Layers, Users } from "lucide-react";
import { useTranslations } from "next-intl";
import { memo } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { useModel } from "@/hooks/use-org";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";

import type { OrgNode } from "./org-layout";

const hidden = "!h-2 !w-2 !min-w-0 !border-0 !bg-transparent";

function Shell({ data, className, children }: { data: OrgNode["data"]; className?: string; children: React.ReactNode }) {
  return (
    <div
      className={cn(
        "relative h-full w-full rounded-xl border bg-card/95 shadow-[0_10px_24px_-16px_rgba(0,0,0,0.6)] backdrop-blur transition-[opacity,border-color,box-shadow,transform] duration-200 hover:-translate-y-px hover:border-foreground/25",
        data.selected && "border-primary shadow-[0_0_0_3px_color-mix(in_srgb,var(--primary)_20%,transparent),0_14px_30px_-14px_var(--primary)]",
        data.match && !data.selected && "border-cyan shadow-[0_0_0_3px_color-mix(in_srgb,var(--cyan)_18%,transparent)]",
        data.dim && "opacity-25",
        className,
      )}
    >
      <Handle type="target" position={Position.Left} className={hidden} isConnectable={false} />
      {children}
      <Handle type="source" position={Position.Right} className={hidden} isConnectable={false} />
    </div>
  );
}

export const CompanyNode = memo(function CompanyNode({ data }: NodeProps<OrgNode>) {
  const t = useTranslations("org");
  const model = useModel();
  const owned = model.state.processes.filter((p) => model.hasRole(p.id, "owner")).length;
  const rows: [string, React.ReactNode, boolean?][] = [
    [t("departments"), model.state.departments.length],
    [t("teams"), model.state.teams.length],
    [t("employees"), model.state.members.length],
    [t("processes"), model.state.processes.length],
    [t("ownership"), `${owned}/${model.state.processes.length}`],
    [t("attention"), model.issueProcesses.length, model.issueProcesses.length > 0],
  ];
  return (
    <Shell data={data} className="px-4 pb-3 pt-12 text-center">
      <span className="absolute -top-9 left-1/2 grid size-[72px] -translate-x-1/2 place-items-center rounded-full border border-primary/40 bg-[radial-gradient(circle_at_50%_35%,var(--elevated),var(--card)_70%)] shadow-[0_0_0_6px_var(--background),0_0_0_7px_color-mix(in_srgb,var(--primary)_20%,transparent),0_0_40px_-6px_var(--primary),0_0_60px_-24px_var(--violet)]">
        <span className="size-[18px] rounded-full bg-primary shadow-[0_0_0_6px_color-mix(in_srgb,var(--primary)_18%,transparent),0_0_22px_var(--primary)]" />
      </span>
      <div className="text-[15px] font-semibold">{model.state.meta.company}</div>
      <div className="text-[11.5px] text-muted-foreground">{t("hq")}</div>
      <dl className="mt-3 grid gap-1.5 text-left text-[12.5px]">
        {rows.map(([label, value, warn]) => (
          <div key={label} className="flex justify-between text-muted-foreground">
            <dt>{label}</dt><dd className={cn("font-mono font-medium text-foreground", warn && "text-warning")}>{value}</dd>
          </div>
        ))}
      </dl>
    </Shell>
  );
});

export const DeptNode = memo(function DeptNode({ data }: NodeProps<OrgNode>) {
  const t = useTranslations("org");
  const model = useModel();
  const toggle = useUI((s) => s.toggleDept);
  const dept = model.dept.get(data.id);
  const members = model.membersOf(data.id);
  return (
    <Shell data={data} className={cn("flex items-center gap-3 px-3", data.collapsed && "border-dashed")}>
      <span className="grid size-9 shrink-0 place-items-center rounded-lg border bg-primary/10 text-primary"><Building2 className="size-4" /></span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold">{dept?.name ?? t("noDepartment")}</div>
        <div className="text-[11.5px] text-muted-foreground">{t("deptMeta", { members: members.length, teams: model.teamsOf(data.id).length })}</div>
      </div>
      <button
        className="nodrag grid size-7 place-items-center rounded-md text-muted-foreground hover:bg-muted hover:text-foreground"
        onClick={(e) => { e.stopPropagation(); toggle(data.id); }}
        title={data.collapsed ? t("expand") : t("collapse")}
      >
        {data.collapsed ? <ChevronRight className="size-4" /> : <ChevronDown className="size-4" />}
      </button>
    </Shell>
  );
});

export const TeamNode = memo(function TeamNode({ data }: NodeProps<OrgNode>) {
  const t = useTranslations("org");
  const model = useModel();
  const team = model.team.get(data.id);
  const lead = team?.lead ? model.member.get(team.lead) : undefined;
  return (
    <Shell data={data} className="flex items-center gap-3 px-3">
      <span className="grid size-8 shrink-0 place-items-center rounded-lg border text-muted-foreground"><Users className="size-4" /></span>
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-medium">{team?.name}</div>
        <div className="truncate text-[11px] text-muted-foreground">{lead ? t("lead", { name: lead.name }) : t("team")}</div>
      </div>
    </Shell>
  );
});

export const MemberNode = memo(function MemberNode({ data }: NodeProps<OrgNode>) {
  const t = useTranslations("org");
  const model = useModel();
  const m = model.member.get(data.id);
  const w = model.workload.find((x) => x.member.id === data.id);
  const max = Math.max(1, ...model.workload.map((x) => x.score));
  if (!m) return null;
  return (
    <Shell data={data} className="flex items-center gap-3 px-3">
      <MemberAvatar member={m} size={38} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-1.5 truncate text-[13px] font-semibold">
          {m.name}{w?.excessive && <span className="size-1.5 shrink-0 rounded-full bg-warning" title={t("excessive")} />}
        </div>
        <div className="truncate text-[11.5px] text-muted-foreground">
          {m.role} · {t("memberMeta", { tasks: model.load.get(m.id) ?? 0, processes: (model.linksOfMember.get(m.id) ?? []).length })}
        </div>
      </div>
      <span className="absolute inset-x-3 -bottom-px h-0.5 overflow-hidden rounded-full">
        <span className="block h-full bg-gradient-to-r from-primary/20 to-primary" style={{ width: `${((w?.score ?? 0) / max) * 100}%` }} />
      </span>
    </Shell>
  );
});

export const ProcessNode = memo(function ProcessNode({ data }: NodeProps<OrgNode>) {
  const t = useTranslations("org");
  const model = useModel();
  const p = model.process.get(data.id);
  if (!p) return null;
  const level = model.level(p.id);
  const owner = model.primaryOwner.get(p.id);
  return (
    <Shell data={data} className="flex items-center gap-2.5 rounded-[10px] pl-3.5 pr-2.5">
      <span className={cn("absolute -left-1 top-1/2 size-2 -translate-y-1/2 rounded-full border-[1.5px] border-[var(--edge-soft)] bg-background", (data.selected || (!data.dim && data.match)) && "border-cyan bg-cyan")} />
      <Layers className="size-3.5 shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12.5px] font-medium">{p.name}</div>
        <div className="truncate text-[11px] text-muted-foreground">{model.systemName(p) || t("noSystem")} · {t("tasks", { count: (model.tasksOf.get(p.id) ?? []).length })}</div>
      </div>
      {level && <span className={cn("size-2 shrink-0 rounded-full", level === "danger" ? "bg-destructive shadow-[0_0_8px_var(--destructive)]" : "bg-warning shadow-[0_0_8px_var(--warning)]")} />}
      {owner ? <MemberAvatar member={model.member.get(owner)} size={22} /> : <span className="rounded-md border border-destructive/40 px-1.5 text-[10.5px] text-destructive">{t("noOwner")}</span>}
    </Shell>
  );
});

export const nodeTypes = { company: CompanyNode, dept: DeptNode, team: TeamNode, member: MemberNode, process: ProcessNode };
