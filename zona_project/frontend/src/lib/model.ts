/**
 * Tashkilot modeli: backend holatidan hisoblangan indekslar va tahlil.
 * Barcha sahifalar (xarita, matritsa, analitika, bo'shliqlar) shu bitta manbadan foydalanadi.
 */
import type {
  Authority, Department, Member, OrgState, Process, ProcessRole, RoleKey, Task, Team, Zone,
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

/* ------------------------------------------------------------------ vaqt yuklamasi
 * Formula backend/zona/timeload.py dagi bilan bir xil:
 * haftalik daqiqa = bir martalik vaqt × haftasiga soni; mas'ul — 100%, 1-zaxira — 15%, keyingilari — 5%.
 * bandlik = (mas'ul + zaxira soatlari) / haftalik sig'im; 85% dan yuqori — ortiqcha, 70% dan — band. */
export const FALLBACK_SHARE = [0.15, 0.05] as const;
export const OVERLOAD = 0.85;
export const BUSY = 0.7;
export const weekMinutes = (t: Task) => (t.minutes || 0) * (t.per_week || 0);
export type LoadStatus = "over" | "busy" | "ok";

export interface TimeLoad {
  member: Member;
  ownerMin: number;
  backupMin: number;
  hours: number;
  capacity: number;
  util: number;
  status: LoadStatus;
  /** zona id (yoki null) -> haftalik daqiqa (mas'ul sifatida) */
  zones: Map<number | null, number>;
  tasks: Task[];
}

export interface Recommendation {
  kind: "reassign" | "capacity";
  task?: Task;
  from: number;
  to?: number;
  hours: number;
}

export interface Workload {
  member: Member;
  tasks: number;
  owned: number;
  approvals: number;
  other: number;
  score: number; // tasks + 3 * (egalik + boshqa rollar)
  excessive: boolean;
  hours: number;
  util: number;
  status: LoadStatus;
}

export interface Model {
  state: OrgState;
  dept: Map<number, Department>;
  team: Map<number, Team>;
  member: Map<number, Member>;
  process: Map<number, Process>;
  task: Map<number, Task>;
  systemName: (p: Process | undefined) => string;
  zone: Map<number, Zone>;
  zoneOf: (p: Process | undefined) => Zone | undefined;
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
  timeLoad: Map<number, TimeLoad>;
  recommendations: Recommendation[];
  totalWeekHours: number;
  /** vaqt ma'lumoti bormi (hech bo'lmasa bitta savolda) */
  hasTime: boolean;
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
  const zones = byId(state.zones ?? []);

  const deptOf = (m: Member) => (m.department && dept.has(m.department) ? m.department : 0);
  const deptOrder = [...state.departments.map((d) => d.id), 0];
  const memberOrder = [...state.members].sort(
    (a, b) => deptOrder.indexOf(deptOf(a)) - deptOrder.indexOf(deptOf(b)) || a.order - b.order || a.id - b.id,
  );
  const rank = new Map(memberOrder.map((m, i) => [m.id, i]));

  const tasksOf = new Map<number, Task[]>();
  const fallbackTasksOf = new Map<number, Task[]>();
  const load = new Map<number, number>();
  // exec: jarayon -> ijrochi -> vazifalar soni (asosiy mas'ul ham, navbatdagilar ham ijrochi).
  // mainExec: faqat asosiy mas'ullar — "ijrochilar bo'lingan" ogohlantirishi uchun.
  const exec = new Map<number, Map<number, number>>();
  const mainExec = new Map<number, Map<number, number>>();
  const bump = (map: Map<number, Map<number, number>>, pid: number, mid: number) => {
    const m = map.get(pid) ?? new Map<number, number>();
    m.set(mid, (m.get(mid) ?? 0) + 1);
    map.set(pid, m);
  };
  for (const t of state.tasks) {
    if (t.process) push(tasksOf, t.process, t);
    for (const f of t.fallbacks ?? []) {
      push(fallbackTasksOf, f.member, t);
      if (t.process) bump(exec, t.process, f.member);
    }
    if (t.owner) load.set(t.owner, (load.get(t.owner) ?? 0) + 1);
    if (t.process && t.owner) {
      bump(exec, t.process, t.owner);
      bump(mainExec, t.process, t.owner);
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
    const execs = [...(mainExec.get(p.id) ?? new Map<number, number>()).entries()].sort((a, b) => b[1] - a[1]);
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

  // vaqt yuklamasi
  const timeLoad = new Map<number, TimeLoad>();
  for (const m of state.members) {
    timeLoad.set(m.id, { member: m, ownerMin: 0, backupMin: 0, hours: 0, capacity: m.capacity || 40, util: 0, status: "ok", zones: new Map(), tasks: [] });
  }
  for (const t of state.tasks) {
    const w = weekMinutes(t);
    const zid = t.process ? process.get(t.process)?.zone ?? null : null;
    const o = t.owner ? timeLoad.get(t.owner) : undefined;
    if (o) {
      o.ownerMin += w;
      o.tasks.push(t);
      o.zones.set(zid, (o.zones.get(zid) ?? 0) + w);
    }
    t.fallbacks.forEach((f, i) => {
      const b = timeLoad.get(f.member);
      if (b) b.backupMin += w * (i === 0 ? FALLBACK_SHARE[0] : FALLBACK_SHARE[1]);
    });
  }
  for (const v of timeLoad.values()) {
    v.hours = (v.ownerMin + v.backupMin) / 60;
    v.util = v.hours / Math.max(v.capacity, 0.1);
    v.status = v.util > OVERLOAD ? "over" : v.util > BUSY ? "busy" : "ok";
  }
  const hasTime = state.tasks.some((t) => weekMinutes(t) > 0);
  const totalWeekHours = state.tasks.reduce((s, t) => s + weekMinutes(t), 0) / 60;
  const recommendations = recommend(timeLoad, process);
  const workload = raw.map((w) => {
    const tl = timeLoad.get(w.member.id)!;
    return {
      ...w, hours: tl.hours, util: tl.util, status: tl.status,
      excessive: hasTime ? tl.status === "over" : active.length > 2 && w.score > avg * 1.35,
    };
  });

  const level = (pid: number): IssueLevel | null => {
    const list = issues.get(pid) ?? [];
    return list.some((i) => i.level === "danger") ? "danger" : list.length ? "warn" : null;
  };

  return {
    state, dept, team, member, process, task,
    systemName: (p) => (p?.system ? systems.get(p.system)?.name ?? "" : ""),
    zone: zones,
    zoneOf: (p) => (p?.zone ? zones.get(p.zone) : undefined),
    tasksOf, fallbackTasksOf, rolesOf, linksOfMember, linksOfProcess,
    link: (pid, mid) => links.get(`${pid}|${mid}`),
    primaryOwner, load, authorities, reports, issues,
    issueProcesses: state.processes.filter((p) => (issues.get(p.id) ?? []).length),
    unassignedTasks: state.tasks.filter((t) => !t.owner),
    orphanTasks: state.tasks.filter((t) => !t.process),
    conflicts, coverage, workload, timeLoad, recommendations, totalWeekHours, hasTime, deptOf,
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

/**
 * Qoidaga asoslangan tavsiyalar (backend timeload.recommendations bilan bir xil):
 * ortiqcha yuklangan xodimning eng ko'p vaqt oladigan savolini avval rahbariga (ish ko'p bo'lganda yordam beradi),
 * keyin shu zonadagi bir xil darajali hamkasbiga, keyin zaxirasiga — bandligi past bo'lsa — o'tkazish.
 * L3, tashqi hamkor va biznes (tasdiqlovchi) almashtiruvchi emas. Yetmasa — sig'im tavsiyasi.
 */
function recommend(load: Map<number, TimeLoad>, process: Map<number, Process>): Recommendation[] {
  const sim = new Map([...load].map(([id, v]) => [id, { ...v }]));
  const recs: Recommendation[] = [];
  const zoneOf = (t: Task) => (t.process ? process.get(t.process)?.zone ?? null : null);
  for (const [mid, v] of [...sim].sort((a, b) => b[1].util - a[1].util)) {
    if (v.status !== "over") continue;
    const need = v.hours - v.capacity * BUSY;
    let moved = 0;
    for (const t of [...v.tasks].sort((a, b) => weekMinutes(b) - weekMinutes(a))) {
      if (moved >= need) break;
      const me = v.member;
      const zone = zoneOf(t);
      const cands = [
        ...(me.manager ? [me.manager] : []),
        ...[...sim].filter(([o, ov]) => o !== mid && ov.member.level === me.level && ov.tasks.some((x) => zoneOf(x) === zone)).map(([o]) => o),
        ...t.fallbacks.map((f) => f.member),
      ];
      const best = [...new Set(cands)].find((c) => {
        const cv = sim.get(c);
        return !!cv && c !== mid && cv.status === "ok" && cv.member.level !== "L3" && cv.member.level !== "EXT"
          && (cv.member.level !== "BIZ" || me.level === "BIZ");
      });
      if (best === undefined) continue;
      const h = weekMinutes(t) / 60;
      recs.push({ kind: "reassign", task: t, from: mid, to: best, hours: Math.round(h * 10) / 10 });
      moved += h;
      const bv = sim.get(best)!;
      bv.hours += h;
      bv.util = bv.hours / Math.max(bv.capacity, 0.1);
      if (bv.util > BUSY) bv.status = "busy";
    }
    if (moved < need) recs.push({ kind: "capacity", from: mid, hours: Math.round((need - moved) * 10) / 10 });
  }
  return recs;
}

/** "1 soat 30 daq" kabi qisqa ko'rinish uchun: soatlarni bir xonali kasr bilan. */
export const fmtHours = (h: number) => (h >= 10 ? Math.round(h).toString() : (Math.round(h * 10) / 10).toString());
