/**
 * Tashkilot modeli: backend holatidan hisoblangan indekslar va tahlil.
 * Barcha sahifalar (xarita, matritsa, analitika, bo'shliqlar) shu bitta manbadan foydalanadi.
 */
import type {
  Authority, Department, Member, OrgState, Process, ProcessRole, RoleKey, Task, Team,
} from "@/lib/api/types";

export const ROLE_ORDER: RoleKey[] = ["owner", "executor", "approver", "supervisor", "contributor", "backup"];
export const PROCESS_ROLES = ROLE_ORDER.filter((r) => r !== "executor") as Exclude<RoleKey, "executor">[];

/** Rol chiziq uslubi: rang emas, shtrix bilan farqlanadi. */
export const ROLE_DASH: Record<RoleKey, string | undefined> = {
  owner: undefined,
  executor: undefined,
  approver: "7 5",
  supervisor: "12 4 2 4",
  contributor: "1 5",
  backup: "3 3",
};
export const ROLE_GLYPH: Record<RoleKey, string> = {
  owner: "E", executor: "I", approver: "T", supervisor: "N", contributor: "Y", backup: "Z",
};

/** Xodim va jarayon o'rtasidagi bog'lanish (bir nechta rol bo'lishi mumkin). */
export interface Link {
  processId: number;
  memberId: number;
  roles: Set<RoleKey>;
  tasks: number; // ijrochi sifatida vazifalar soni
  top: RoleKey;
}

export type IssueLevel = "danger" | "warn";
export interface Issue {
  level: IssueLevel;
  code: "no_owner" | "multi_owner" | "split_exec" | "unassigned" | "empty" | "no_supervisor" | "no_backup";
  count?: number;
}

export interface Workload {
  member: Member;
  tasks: number;
  owned: number;
  approvals: number;
  other: number;
  score: number; // tasks + 3 * (egalik + boshqa rollar)
  excessive: boolean;
}

export interface Model {
  state: OrgState;
  dept: Map<number, Department>;
  team: Map<number, Team>;
  member: Map<number, Member>;
  process: Map<number, Process>;
  task: Map<number, Task>;
  systemName: (p: Process | undefined) => string;
  tasksOf: Map<number, Task[]>;
  /** xodim -> u navbatdagi mas'ul bo'lgan vazifalar */
  fallbackTasksOf: Map<number, Task[]>;
  rolesOf: Map<number, ProcessRole[]>;
  linksOfMember: Map<number, Link[]>;
  linksOfProcess: Map<number, Link[]>;
  link: (processId: number, memberId: number) => Link | undefined;
  primaryOwner: Map<number, number | null>;
  load: Map<number, number>;
  authorities: Map<number, Authority[]>;
  reports: Map<number, Member[]>;
  issues: Map<number, Issue[]>;
  issueProcesses: Process[];
  unassignedTasks: Task[];
  orphanTasks: Task[];
  conflicts: number;
  coverage: { owner: number; supervisor: number; approver: number; backup: number; tasks: number };
  workload: Workload[];
  deptOf: (m: Member) => number;
  teamsOf: (deptId: number) => Team[];
  membersOf: (deptId: number) => Member[];
  membersOfTeam: (teamId: number | null, deptId: number) => Member[];
  memberOrder: Member[];
  hasRole: (processId: number, role: RoleKey) => boolean;
  peers: (memberId: number) => Map<number, number>;
  level: (processId: number) => IssueLevel | null;
}

const push = <K, V>(map: Map<K, V[]>, key: K, value: V) => {
  const list = map.get(key);
  if (list) list.push(value);
  else map.set(key, [value]);
};

export function buildModel(state: OrgState): Model {
  const byId = <T extends { id: number }>(list: T[]) => new Map(list.map((x) => [x.id, x]));
  const dept = byId(state.departments);
  const team = byId(state.teams);
  const member = byId(state.members);
  const process = byId(state.processes);
  const task = byId(state.tasks);
  const systems = byId(state.systems);

  const deptOf = (m: Member) => (m.department && dept.has(m.department) ? m.department : 0);
  const deptOrder = [...state.departments.map((d) => d.id), 0];
  const memberOrder = [...state.members].sort(
    (a, b) => deptOrder.indexOf(deptOf(a)) - deptOrder.indexOf(deptOf(b)) || a.order - b.order || a.id - b.id,
  );
  const rank = new Map(memberOrder.map((m, i) => [m.id, i]));

  const tasksOf = new Map<number, Task[]>();
  const fallbackTasksOf = new Map<number, Task[]>();
  const load = new Map<number, number>();
  const exec = new Map<number, Map<number, number>>();
  for (const t of state.tasks) {
    if (t.process) push(tasksOf, t.process, t);
    for (const f of t.fallbacks ?? []) push(fallbackTasksOf, f.member, t);
    if (t.owner) load.set(t.owner, (load.get(t.owner) ?? 0) + 1);
    if (t.process && t.owner) {
      const m = exec.get(t.process) ?? new Map<number, number>();
      m.set(t.owner, (m.get(t.owner) ?? 0) + 1);
      exec.set(t.process, m);
    }
  }
  const rolesOf = new Map<number, ProcessRole[]>();
  for (const r of state.roles) push(rolesOf, r.process, r);

  const links = new Map<string, Link>();
  const linksOfMember = new Map<number, Link[]>();
  const linksOfProcess = new Map<number, Link[]>();
  const ensure = (processId: number, memberId: number) => {
    const key = `${processId}|${memberId}`;
    let l = links.get(key);
    if (!l) {
      l = { processId, memberId, roles: new Set(), tasks: 0, top: "executor" };
      links.set(key, l);
      push(linksOfMember, memberId, l);
      push(linksOfProcess, processId, l);
    }
    return l;
  };
  for (const [pid, m] of exec) for (const [mid, n] of m) { const l = ensure(pid, mid); l.roles.add("executor"); l.tasks = n; }
  for (const r of state.roles) if (process.has(r.process) && member.has(r.member)) ensure(r.process, r.member).roles.add(r.role);
  for (const l of links.values()) l.top = ROLE_ORDER.find((r) => l.roles.has(r)) ?? "executor";

  const hasRole = (pid: number, role: RoleKey) =>
    role === "executor" ? exec.has(pid) : (rolesOf.get(pid) ?? []).some((r) => r.role === role);

  const primaryOwner = new Map<number, number | null>();
  const issues = new Map<number, Issue[]>();
  let conflicts = 0;
  for (const p of state.processes) {
    const owners = (rolesOf.get(p.id) ?? []).filter((r) => r.role === "owner").map((r) => r.member)
      .sort((a, b) => (rank.get(a) ?? 1e6) - (rank.get(b) ?? 1e6));
    const execs = [...(exec.get(p.id) ?? new Map<number, number>()).entries()].sort((a, b) => b[1] - a[1]);
    primaryOwner.set(p.id, owners[0] ?? execs[0]?.[0] ?? null);
    const tasks = tasksOf.get(p.id) ?? [];
    const unassigned = tasks.filter((t) => !t.owner).length;
    const list: Issue[] = [];
    if (!owners.length) list.push({ level: "danger", code: "no_owner" });
    if (owners.length > 1) { list.push({ level: "warn", code: "multi_owner", count: owners.length }); conflicts++; }
    if (execs.length > 1) list.push({ level: "warn", code: "split_exec", count: execs.length });
    if (unassigned) list.push({ level: "danger", code: "unassigned", count: unassigned });
    if (!tasks.length) list.push({ level: "warn", code: "empty" });
    issues.set(p.id, list);
  }

  const authorities = new Map<number, Authority[]>();
  for (const a of state.authorities) push(authorities, a.member, a);
  const reports = new Map<number, Member[]>();
  for (const m of state.members) if (m.manager) push(reports, m.manager, m);

  const P = Math.max(1, state.processes.length);
  const coverage = {
    owner: state.processes.filter((p) => hasRole(p.id, "owner")).length / P,
    supervisor: state.processes.filter((p) => hasRole(p.id, "supervisor") || hasRole(p.id, "approver")).length / P,
    approver: state.processes.filter((p) => hasRole(p.id, "approver")).length / P,
    backup: state.processes.filter((p) => hasRole(p.id, "backup")).length / P,
    tasks: state.tasks.length ? state.tasks.filter((t) => t.owner).length / state.tasks.length : 1,
  };

  const raw = memberOrder.map((m) => {
    const ls = linksOfMember.get(m.id) ?? [];
    const owned = ls.filter((l) => l.roles.has("owner")).length;
    const approvals = ls.filter((l) => l.roles.has("approver")).length;
    const other = ls.filter((l) => l.roles.has("supervisor") || l.roles.has("contributor") || l.roles.has("backup")).length;
    const tasks = load.get(m.id) ?? 0;
    return { member: m, tasks, owned, approvals, other, score: tasks + 3 * (owned + approvals + other), excessive: false };
  });
  const active = raw.filter((w) => w.score > 0);
  const avg = active.reduce((s, w) => s + w.score, 0) / Math.max(1, active.length);
  const workload = raw.map((w) => ({ ...w, excessive: active.length > 2 && w.score > avg * 1.35 }));

  const level = (pid: number): IssueLevel | null => {
    const list = issues.get(pid) ?? [];
    return list.some((i) => i.level === "danger") ? "danger" : list.length ? "warn" : null;
  };

  return {
    state, dept, team, member, process, task,
    systemName: (p) => (p?.system ? systems.get(p.system)?.name ?? "" : ""),
    tasksOf, fallbackTasksOf, rolesOf, linksOfMember, linksOfProcess,
    link: (pid, mid) => links.get(`${pid}|${mid}`),
    primaryOwner, load, authorities, reports, issues,
    issueProcesses: state.processes.filter((p) => (issues.get(p.id) ?? []).length),
    unassignedTasks: state.tasks.filter((t) => !t.owner),
    orphanTasks: state.tasks.filter((t) => !t.process),
    conflicts, coverage, workload, deptOf,
    teamsOf: (deptId) => state.teams.filter((t) => t.department === deptId),
    membersOf: (deptId) => memberOrder.filter((m) => deptOf(m) === deptId),
    membersOfTeam: (teamId, deptId) => memberOrder.filter((m) => deptOf(m) === deptId && (m.team ?? null) === teamId),
    memberOrder, hasRole,
    peers: (mid) => {
      const peers = new Map<number, number>();
      for (const l of linksOfMember.get(mid) ?? []) for (const o of linksOfProcess.get(l.processId) ?? []) {
        if (o.memberId !== mid) peers.set(o.memberId, (peers.get(o.memberId) ?? 0) + 1);
      }
      return peers;
    },
    level,
  };
}

export function initials(name: string): string {
  const words = name.split(/\s+/).filter(Boolean);
  if (words.length > 1) return (words[0][0] + words[1][0]).toUpperCase();
  const w = words[0] ?? "?";
  return w.slice(0, 1).toUpperCase() + w.slice(1, 2);
}
