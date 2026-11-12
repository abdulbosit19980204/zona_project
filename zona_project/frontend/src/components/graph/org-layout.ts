/**
 * Tashkilot xaritasi joylashuvi: Kompaniya → Bo'lim → Jamoa → Xodim → Jarayon (chapdan o'ngga).
 * Jarayonlar egasi bo'yicha tartiblanadi, xodim o'z birinchi jarayoni qatorida turadi —
 * shuning uchun bog'lanishlar deyarli kesishmaydi.
 */
import type { Edge, Node } from "@xyflow/react";

import type { RoleKey } from "@/lib/api/types";
import { ROLE_ORDER, type Model } from "@/lib/model";

export const COL = { company: 0, dept: 300, team: 580, member: 860, process: 1190 } as const;
export const SIZE = {
  company: { w: 230, h: 250 }, dept: { w: 230, h: 64 }, team: { w: 230, h: 56 },
  member: { w: 260, h: 64 }, process: { w: 300, h: 52 },
} as const;
const GAP = { process: 62, member: 84, team: 76, dept: 84, top: 40 };

export type OrgNodeKind = "company" | "dept" | "team" | "member" | "process";

export interface OrgNodeData extends Record<string, unknown> {
  kind: OrgNodeKind;
  id: number;
  dim: boolean;
  selected: boolean;
  match: boolean;
  collapsed?: boolean;
}

export interface RoleEdgeData extends Record<string, unknown> {
  role: RoleKey | "struct";
  label: string;
  highlight: boolean;
  dim: boolean;
}

export type OrgNode = Node<OrgNodeData>;
export type OrgEdge = Edge<RoleEdgeData>;

export interface LayoutOptions {
  scope: number | null;
  collapsed: number[];
  hiddenRoles: RoleKey[];
  onlyIssues: boolean;
  roleLabel: (role: RoleKey) => string;
}

export interface OrgGraph {
  nodes: OrgNode[];
  edges: OrgEdge[];
  processCount: number;
}

export const nodeKey = (kind: OrgNodeKind, id: number) => `${kind}:${id}`;

export function layoutOrg(model: Model, opts: LayoutOptions): OrgGraph {
  const depts = [...model.state.departments, ...(model.membersOf(0).length ? [{ id: 0, name: "", description: "", order: 999 }] : [])]
    .filter((d) => !opts.scope || d.id === opts.scope);
  const collapsed = new Set(opts.collapsed);
  const anchor = new Map<number, string>(); // xodim -> xaritadagi tugun (yig'ilgan bo'limda — bo'lim)
  const visibleMembers: number[] = [];
  for (const d of depts) for (const m of model.membersOf(d.id)) {
    if (collapsed.has(d.id)) anchor.set(m.id, nodeKey("dept", d.id));
    else { anchor.set(m.id, nodeKey("member", m.id)); visibleMembers.push(m.id); }
  }
  const rank = new Map(model.memberOrder.map((m, i) => [m.id, i]));

  let processes = model.state.processes.filter((p) =>
    (model.linksOfProcess.get(p.id) ?? []).some((l) => anchor.has(l.memberId)) || (!opts.scope && !(model.linksOfProcess.get(p.id) ?? []).length));
  if (opts.onlyIssues) processes = processes.filter((p) => (model.issues.get(p.id) ?? []).length);
  const rankOf = (pid: number) => { const o = model.primaryOwner.get(pid); return o ? rank.get(o) ?? 1e6 : 1e6; };
  processes.sort((a, b) => rankOf(a.id) - rankOf(b.id) || a.order - b.order || a.id - b.id);

  const pos = new Map<string, { x: number; y: number; w: number; h: number }>();
  const centerY = (key: string) => { const p = pos.get(key)!; return p.y + p.h / 2; };
  processes.forEach((p, i) => pos.set(nodeKey("process", p.id), { x: COL.process, y: GAP.top + i * GAP.process, ...wh("process") }));

  // xodim: o'zi egalik qilgan birinchi jarayon qatorida
  let prev: number | null = null;
  for (const mid of visibleMembers) {
    const first = processes.find((p) => model.primaryOwner.get(p.id) === mid);
    const want = first ? centerY(nodeKey("process", first.id)) - SIZE.member.h / 2 : null;
    const min: number = prev === null ? GAP.top : prev + GAP.member;
    const y: number = want === null ? min : Math.max(want, min);
    pos.set(nodeKey("member", mid), { x: COL.member, y, ...wh("member") });
    prev = y;
  }
  // jamoa: birinchi a'zosi qatorida; bo'lim: birinchi jamoasi/a'zosi qatorida
  const teamsShown: number[] = [];
  prev = null;
  for (const d of depts) {
    if (collapsed.has(d.id)) continue;
    for (const team of model.teamsOf(d.id)) {
      const ms = model.membersOfTeam(team.id, d.id);
      if (!ms.length) continue;
      const want = centerY(nodeKey("member", ms[0].id)) - SIZE.team.h / 2;
      const y: number = prev === null ? want : Math.max(want, prev + GAP.team);
      pos.set(nodeKey("team", team.id), { x: COL.team, y, ...wh("team") });
      teamsShown.push(team.id);
      prev = y;
    }
  }
  prev = null;
  for (const d of depts) {
    const ys = collapsed.has(d.id)
      ? processes.filter((p) => anchor.get(model.primaryOwner.get(p.id) ?? -1) === nodeKey("dept", d.id)).map((p) => centerY(nodeKey("process", p.id)))
      : model.membersOf(d.id).map((m) => centerY(nodeKey("member", m.id)));
    const want = ys.length ? ys[0] - SIZE.dept.h / 2 : null;
    const min: number = prev === null ? GAP.top : prev + GAP.dept;
    const y: number = want === null ? min : Math.max(want, min);
    pos.set(nodeKey("dept", d.id), { x: COL.dept, y, ...wh("dept") });
    prev = y;
  }
  pos.set(nodeKey("company", 0), { x: COL.company, y: GAP.top + 30, ...wh("company") });

  const nodes: OrgNode[] = [...pos.entries()].map(([key, p]) => {
    const [kind, id] = key.split(":") as [OrgNodeKind, string];
    return {
      id: key, type: kind, position: { x: p.x, y: p.y }, width: p.w, height: p.h, draggable: false,
      data: { kind, id: Number(id), dim: false, selected: false, match: false, collapsed: kind === "dept" ? collapsed.has(Number(id)) : undefined },
    };
  });

  const edges: OrgEdge[] = [];
  const struct = (source: string, target: string) =>
    edges.push({ id: `${source}>${target}`, source, target, type: "role", data: { role: "struct", label: "", highlight: false, dim: false } });
  for (const d of depts) struct(nodeKey("company", 0), nodeKey("dept", d.id));
  for (const tid of teamsShown) struct(nodeKey("dept", model.team.get(tid)!.department), nodeKey("team", tid));
  for (const mid of visibleMembers) {
    const m = model.member.get(mid)!;
    const teamKey = m.team && teamsShown.includes(m.team) ? nodeKey("team", m.team) : nodeKey("dept", model.deptOf(m));
    struct(teamKey, nodeKey("member", mid));
  }
  // rol bog'lanishlari (yig'ilgan bo'limda bir nechta xodimniki birlashadi)
  const merged = new Map<string, { roles: Set<RoleKey>; labels: string[] }>();
  for (const p of processes) for (const l of model.linksOfProcess.get(p.id) ?? []) {
    const source = anchor.get(l.memberId);
    if (!source) continue;
    const roles = [...l.roles].filter((r) => !opts.hiddenRoles.includes(r));
    if (!roles.length) continue;
    const key = `${source}>${nodeKey("process", p.id)}`;
    const label = roles.map((r) => (r === "executor" ? `${opts.roleLabel(r)} · ${l.tasks}` : opts.roleLabel(r))).join(" · ");
    const cur = merged.get(key);
    if (cur) { roles.forEach((r) => cur.roles.add(r)); cur.labels.push(label); }
    else merged.set(key, { roles: new Set(roles), labels: [label] });
  }
  for (const [key, v] of merged) {
    const [source, target] = key.split(">");
    const role = ROLE_ORDER.find((r) => v.roles.has(r)) ?? "executor";
    edges.push({
      id: key, source, target, type: "role",
      data: { role, label: source.startsWith("dept") ? `${v.labels.length}` : v.labels[0], highlight: false, dim: false },
    });
  }
  return { nodes, edges, processCount: processes.length };
}

function wh(kind: keyof typeof SIZE) {
  return { w: SIZE[kind].w, h: SIZE[kind].h };
}

/** Tanlangan tugun bilan bog'liq tugun va bog'lanishlar (yuqoriga — tuzilma, pastga — mas'uliyat). */
export function relatedTo(key: string, edges: OrgEdge[]): { nodes: Set<string>; edges: Set<string> } | null {
  if (!key || key.startsWith("company")) return null;
  const nodes = new Set([key]);
  const ids = new Set<string>();
  const up = (k: string) => {
    for (const e of edges) if (e.target === k && e.data?.role === "struct") { ids.add(e.id); nodes.add(e.source); up(e.source); }
  };
  const down = (k: string, depth: number) => {
    for (const e of edges) if (e.source === k) { ids.add(e.id); nodes.add(e.target); if (depth > 0) down(e.target, depth - 1); }
  };
  if (key.startsWith("process")) {
    for (const e of edges) if (e.target === key) { ids.add(e.id); nodes.add(e.source); up(e.source); }
  } else if (key.startsWith("member")) { down(key, 0); up(key); }
  else if (key.startsWith("team")) { down(key, 1); up(key); }
  else if (key.startsWith("dept")) { down(key, 2); up(key); }
  return { nodes, edges: ids };
}
