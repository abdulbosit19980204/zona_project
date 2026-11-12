"use client";

/**
 * Xodim 360° radial xaritasi: markazda xodim.
 *  chap   — mas'uliyat (egasi / ijrochi bo'lgan jarayonlar)
 *  o'ng   — vakolat va ikkilamchi rollar (tasdiqlovchi, nazoratchi, yordamchi, zaxira) + vakolatlar
 *  tepa   — rahbar; past — bo'ysunuvchilar; tashqi halqa — umumiy jarayonlardagi hamkorlar.
 */
import { BaseEdge, EdgeLabelRenderer, Handle, Position, type Edge, type EdgeProps, type Node, type NodeProps } from "@xyflow/react";
import { Layers, ShieldCheck } from "lucide-react";
import { useTranslations } from "next-intl";
import { memo } from "react";

import { MemberAvatar } from "@/components/common/member-avatar";
import { RoleGlyph } from "@/components/common/role";
import { useModel } from "@/hooks/use-org";
import type { RoleKey } from "@/lib/api/types";
import { ROLE_DASH, ROLE_ORDER, type Link, type Model } from "@/lib/model";
import { cn } from "@/lib/utils";

export interface RadialData extends Record<string, unknown> {
  kind: "me" | "proc" | "auth" | "person";
  id: number;
  role?: RoleKey;
  tasks?: number;
  relation?: "manager" | "report" | "peer";
  dim: boolean;
}
export interface RadialEdgeData extends Record<string, unknown> {
  role: RoleKey | "struct";
  label: string;
  highlight: boolean;
  dim: boolean;
}
type RNode = Node<RadialData>;
type REdge = Edge<RadialEdgeData>;

const SIZE = { me: [300, 150], proc: [240, 46], auth: [240, 46], person: [210, 52] } as const;
const R1 = 380, GAP = 58, COL = 280;

/** Yon sektor: vertikal oraliq qat'iy (qoplanmaydi), ko'p bo'lsa ikki ustun. */
function sector<T>(items: T[], side: -1 | 1) {
  const n = items.length;
  const cols = n > 12 ? 2 : 1;
  const counts = cols === 2 ? [Math.ceil(n / 2), Math.floor(n / 2)] : [n];
  return items.map((item, i) => {
    const col = cols === 2 ? i % 2 : 0;
    const idx = cols === 2 ? Math.floor(i / 2) : i;
    const count = counts[col];
    const y = (idx - (count - 1) / 2) * GAP;
    const r = Math.max(R1, (count * GAP) / 2 / 0.85) + col * COL;
    const x = side * Math.sqrt(Math.max(0, r * r - y * y));
    return { item, x, y, r, angle: Math.atan2(y, x) };
  });
}

export function layoutRadial(model: Model, memberId: number, roleLabel: (r: RoleKey) => string) {
  const nodes: RNode[] = [];
  const edges: REdge[] = [];
  // Omit<> indeks imzoli tipda maydonlarni yo'qotadi — shuning uchun aniq tip.
  const add = (id: string, data: Pick<RadialData, "kind" | "id" | "role" | "tasks" | "relation">, cx: number, cy: number) => {
    const [w, h] = SIZE[data.kind];
    nodes.push({ id, type: data.kind, position: { x: cx - w / 2, y: cy - h / 2 }, width: w, height: h, draggable: false, data: { ...data, dim: false } });
  };
  const edge = (source: string, target: string, role: RoleKey | "struct", label: string) =>
    edges.push({ id: `${source}>${target}`, source, target, type: "radial", data: { role, label, highlight: false, dim: false } });

  add("me", { kind: "me", id: memberId }, 0, 0);
  const links = [...(model.linksOfMember.get(memberId) ?? [])].sort((a, b) => ROLE_ORDER.indexOf(a.top) - ROLE_ORDER.indexOf(b.top) || b.tasks - a.tasks);
  const resp = links.filter((l) => l.roles.has("owner") || l.roles.has("executor"));
  const other = links.filter((l) => !l.roles.has("owner") && !l.roles.has("executor"));
  const authorities = model.authorities.get(memberId) ?? [];
  const label = (l: Link) => ROLE_ORDER.filter((r) => l.roles.has(r)).map((r) => (r === "executor" ? `${roleLabel(r)} · ${l.tasks}` : roleLabel(r))).join(" · ");

  const angles = new Map<number, number>();
  let maxR = R1;
  for (const s of sector(resp, -1)) {
    add(`p:${s.item.processId}`, { kind: "proc", id: s.item.processId, role: s.item.top, tasks: s.item.tasks }, s.x, s.y);
    edge("me", `p:${s.item.processId}`, s.item.top, label(s.item));
    angles.set(s.item.processId, s.angle);
    maxR = Math.max(maxR, s.r);
  }
  const right = [...other.map((l) => ({ link: l, auth: null })), ...authorities.map((a) => ({ link: null, auth: a }))];
  for (const s of sector(right, 1)) {
    if (s.item.link) {
      const l = s.item.link;
      add(`p:${l.processId}`, { kind: "proc", id: l.processId, role: l.top, tasks: l.tasks }, s.x, s.y);
      edge("me", `p:${l.processId}`, l.top, label(l));
      angles.set(l.processId, s.angle);
    } else if (s.item.auth) {
      add(`a:${s.item.auth.id}`, { kind: "auth", id: s.item.auth.id }, s.x, s.y);
      edge("me", `a:${s.item.auth.id}`, "approver", "");
    }
    maxR = Math.max(maxR, s.r);
  }
  const me = model.member.get(memberId);
  const manager = me?.manager ? model.member.get(me.manager) : undefined;
  if (manager) { add(`m:${manager.id}`, { kind: "person", id: manager.id, relation: "manager" }, 0, -250); edge(`m:${manager.id}`, "me", "struct", ""); }
  const reports = model.reports.get(memberId) ?? [];
  reports.forEach((r, i) => {
    add(`m:${r.id}`, { kind: "person", id: r.id, relation: "report" }, (i - (reports.length - 1) / 2) * 230, 250);
    edge("me", `m:${r.id}`, "struct", "");
  });
  // hamkorlar: umumiy jarayonlari burchagining o'rtachasida
  const skip = new Set([memberId, manager?.id, ...reports.map((r) => r.id)]);
  const peers = new Map<number, number[]>();
  for (const l of links) for (const o of model.linksOfProcess.get(l.processId) ?? []) {
    if (skip.has(o.memberId)) continue;
    const list = peers.get(o.memberId) ?? [];
    list.push(l.processId);
    peers.set(o.memberId, list);
  }
  const R2 = maxR + 340;
  const placed = [...peers.entries()].map(([mid, pids]) => ({
    mid, pids, angle: pids.reduce((s, pid) => s + (angles.get(pid) ?? 0), 0) / pids.length,
  })).sort((a, b) => a.angle - b.angle);
  for (let i = 1; i < placed.length; i++) if (placed[i].angle - placed[i - 1].angle < 0.16) placed[i].angle = placed[i - 1].angle + 0.16;
  for (const p of placed) {
    add(`m:${p.mid}`, { kind: "person", id: p.mid, relation: "peer" }, Math.cos(p.angle) * R2, Math.sin(p.angle) * R2);
    for (const pid of p.pids) {
      const l = model.link(pid, p.mid);
      edge(`p:${pid}`, `m:${p.mid}`, l?.top ?? "executor", l ? label(l) : "");
    }
  }
  return { nodes, edges, stats: { resp: resp.length, other: other.length, authorities: authorities.length, peers: placed.length } };
}

const center = "!left-1/2 !top-1/2 !h-1 !w-1 !min-w-0 !-translate-x-1/2 !-translate-y-1/2 !border-0 !bg-transparent";

function Box({ data, className, children }: { data: RadialData; className?: string; children: React.ReactNode }) {
  return (
    <div className={cn("relative h-full w-full rounded-xl border bg-card/95 shadow-[0_10px_24px_-16px_rgba(0,0,0,.6)] backdrop-blur transition-opacity", data.dim && "opacity-25", className)}>
      <Handle type="target" position={Position.Top} className={center} isConnectable={false} />
      {children}
      <Handle type="source" position={Position.Bottom} className={center} isConnectable={false} />
    </div>
  );
}

export const MeNode = memo(function MeNode({ data }: NodeProps<RNode>) {
  const t = useTranslations("panel");
  const model = useModel();
  const m = model.member.get(data.id);
  if (!m) return null;
  const dept = m.department ? model.dept.get(m.department) : undefined;
  return (
    <Box data={data} className="border-primary/50 px-4 pb-3 pt-11 text-center shadow-[0_0_0_4px_color-mix(in_srgb,var(--primary)_14%,transparent)]">
      <span className="absolute -top-9 left-1/2 -translate-x-1/2 rounded-full shadow-[0_0_0_5px_var(--background),0_0_0_6px_color-mix(in_srgb,var(--primary)_45%,transparent),0_0_34px_-4px_var(--primary)]">
        <MemberAvatar member={m} size={64} />
      </span>
      <div className="text-[15px] font-semibold">{m.name}</div>
      <div className="text-xs text-muted-foreground">{m.role}{dept ? ` · ${dept.name}` : ""}</div>
      <div className="mt-2 flex justify-center gap-3 text-[11.5px] text-muted-foreground">
        <span><b className="font-mono text-foreground">{model.load.get(m.id) ?? 0}</b> {t("tasks")}</span>
        <span><b className="font-mono text-foreground">{(model.linksOfMember.get(m.id) ?? []).length}</b> {t("processes")}</span>
        <span><b className="font-mono text-foreground">{(model.authorities.get(m.id) ?? []).length}</b> {t("authority")}</span>
      </div>
    </Box>
  );
});

export const ProcNode = memo(function ProcNode({ data }: NodeProps<RNode>) {
  const model = useModel();
  const p = model.process.get(data.id);
  if (!p) return null;
  return (
    <Box data={data} className="flex items-center gap-2.5 px-3">
      {data.role ? <RoleGlyph role={data.role} /> : <Layers className="size-4" />}
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12.5px] font-medium" title={p.name}>{p.name}</div>
        <div className="truncate text-[11px] text-muted-foreground">{model.systemName(p)}{data.tasks ? ` · ${data.tasks}` : ""}</div>
      </div>
    </Box>
  );
});

export const AuthNode = memo(function AuthNode({ data }: NodeProps<RNode>) {
  const model = useModel();
  const a = model.state.authorities.find((x) => x.id === data.id);
  if (!a) return null;
  return (
    <Box data={data} className="flex items-center gap-2.5 border-dashed border-violet/60 px-3">
      <ShieldCheck className="size-4 shrink-0 text-violet" />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[12.5px] font-medium" title={a.title}>{a.title}</div>
        <div className="truncate text-[11px] text-muted-foreground">{a.scope}</div>
      </div>
    </Box>
  );
});

export const PersonNode = memo(function PersonNode({ data }: NodeProps<RNode>) {
  const model = useModel();
  const m = model.member.get(data.id);
  if (!m) return null;
  return (
    <Box data={data} className="flex cursor-pointer items-center gap-2.5 px-3 hover:border-primary/50">
      <MemberAvatar member={m} size={30} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] font-semibold">{m.name}</div>
        <div className="truncate text-[11px] text-muted-foreground">{m.role}</div>
      </div>
    </Box>
  );
});

export const RadialEdge = memo(function RadialEdge({ id, sourceX, sourceY, targetX, targetY, data }: EdgeProps<REdge>) {
  const mx = (sourceX + targetX) / 2;
  const path = `M${sourceX},${sourceY} C${mx},${sourceY} ${mx},${targetY} ${targetX},${targetY}`;
  const role = data?.role ?? "struct";
  const stroke = data?.highlight ? "var(--primary)" : role === "struct" ? "var(--edge-struct)" : role === "owner" ? "var(--edge-strong)" : "var(--edge-soft)";
  return (
    <>
      <BaseEdge
        id={id} path={path}
        style={{ stroke, strokeWidth: role === "owner" ? 1.9 : 1.3, strokeDasharray: role === "struct" ? undefined : ROLE_DASH[role], opacity: data?.dim ? 0.08 : 1 }}
      />
      {data?.highlight && (
        <>
          <path d={path} fill="none" stroke="var(--cyan)" strokeWidth={1.6} className="edge-flow" />
          {data.label && (
            <EdgeLabelRenderer>
              <div className="pointer-events-none absolute rounded-md border border-primary/40 bg-background px-1.5 py-px text-[10.5px] text-primary"
                style={{ transform: `translate(-50%,-50%) translate(${mx}px, ${(sourceY + targetY) / 2}px)` }}>
                {data.label}
              </div>
            </EdgeLabelRenderer>
          )}
        </>
      )}
    </>
  );
});

export const radialNodeTypes = { me: MeNode, proc: ProcNode, auth: AuthNode, person: PersonNode };
export const radialEdgeTypes = { radial: RadialEdge };
