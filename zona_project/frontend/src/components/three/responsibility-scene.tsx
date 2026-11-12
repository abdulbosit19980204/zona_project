"use client";

import { Html, Line, OrbitControls } from "@react-three/drei";
import { Canvas, type ThreeEvent } from "@react-three/fiber";
import { useMemo, useState } from "react";

import type { RoleKey } from "@/lib/api/types";
import { ROLE_DASH, type Model } from "@/lib/model";

type Vec3 = [number, number, number];

export interface ScenePalette {
  background: string;
  grid: string;
  primary: string;
  violet: string;
  cyan: string;
  warning: string;
  danger: string;
  muted: string;
  text: string;
}

interface SceneNode { key: string; pos: Vec3; label: string; sub?: string }
interface SceneEdge { member: number; process: number; role: RoleKey; from: Vec3; to: Vec3 }

/** Kompaniya markazda, bo'limlar halqada, xodimlar bo'lim atrofida, jarayonlar tashqi yuqori halqada. */
function layout3d(model: Model, inScope: (deptId: number) => boolean, hidden: RoleKey[]) {
  const depts = [...model.state.departments.map((d) => d.id), 0].filter((d) => model.membersOf(d).length && inScope(d));
  const R = Math.max(7, depts.length * 2.8);
  const deptNodes: (SceneNode & { radius: number; id: number })[] = [];
  const memberPos = new Map<number, Vec3>();
  const memberNodes: (SceneNode & { id: number })[] = [];

  depts.forEach((d, i) => {
    const a = (i / depts.length) * Math.PI * 2;
    const c: Vec3 = [R * Math.cos(a), 0, R * Math.sin(a)];
    const ms = model.membersOf(d);
    const r = 1.1 + ms.length * 0.32;
    deptNodes.push({ key: `dept:${d}`, id: d, pos: c, radius: r + 0.5, label: model.dept.get(d)?.name ?? "—" });
    ms.forEach((m, j) => {
      const b = a + (j / ms.length) * Math.PI * 2;
      const p: Vec3 = [c[0] + r * Math.cos(b), 0.55, c[2] + r * Math.sin(b)];
      memberPos.set(m.id, p);
      memberNodes.push({ key: `member:${m.id}`, id: m.id, pos: p, label: m.name, sub: m.role });
    });
  });

  // Jarayonlar: bog'langan xodimlar yo'nalishi bo'yicha tartiblanib, tashqi halqaga teng taqsimlanadi.
  const angled = model.state.processes.flatMap((p) => {
    const links = (model.linksOfProcess.get(p.id) ?? []).filter((l) => memberPos.has(l.memberId));
    if (!links.length) return [];
    let x = 0;
    let z = 0;
    for (const l of links) {
      const w = l.roles.has("owner") ? 3 : 1;
      const mp = memberPos.get(l.memberId) as Vec3;
      x += mp[0] * w;
      z += mp[2] * w;
    }
    return [{ p, angle: Math.atan2(z, x) }];
  }).sort((a, b) => a.angle - b.angle);
  const PR = R + 6 + angled.length * 0.04;
  const offset = angled[0]?.angle ?? 0;
  const processPos = new Map<number, Vec3>();
  const processNodes: (SceneNode & { id: number })[] = angled.map(({ p }, k) => {
    const a = offset + (k / angled.length) * Math.PI * 2;
    const pos: Vec3 = [PR * Math.cos(a), k % 2 ? 3.2 : 4.6, PR * Math.sin(a)];
    processPos.set(p.id, pos);
    return { key: `process:${p.id}`, id: p.id, pos, label: p.name, sub: model.systemName(p) };
  });

  const edges: SceneEdge[] = [];
  for (const [pid, to] of processPos) {
    for (const l of model.linksOfProcess.get(pid) ?? []) {
      const from = memberPos.get(l.memberId);
      if (!from) continue;
      const role = [...l.roles].find((r) => !hidden.includes(r));
      if (!role) continue;
      edges.push({ member: l.memberId, process: pid, role: l.roles.has("owner") && !hidden.includes("owner") ? "owner" : role, from, to });
    }
  }
  return { R, PR, deptNodes, memberNodes, processNodes, edges };
}

export function ResponsibilityScene({ model, palette, selected, onSelect, hiddenRoles, scope }: {
  model: Model;
  palette: ScenePalette;
  selected: string | null;
  onSelect: (key: string | null) => void;
  hiddenRoles: RoleKey[];
  scope: number | null;
}) {
  const [hover, setHover] = useState<string | null>(null);
  const scene = useMemo(
    () => layout3d(model, (d) => !scope || d === scope, hiddenRoles),
    [model, scope, hiddenRoles],
  );

  // Tanlangan/ustidagi tugunga bog'liq hamma narsa yorqin, qolgani xira.
  const focus = hover ?? selected;
  const related = useMemo(() => {
    if (!focus) return null;
    const [kind, raw] = focus.split(":");
    const id = Number(raw);
    const set = new Set<string>([focus]);
    for (const e of scene.edges) {
      const m = model.member.get(e.member);
      const hit = (kind === "member" && e.member === id) || (kind === "process" && e.process === id) ||
        (kind === "dept" && !!m && model.deptOf(m) === id);
      if (hit) { set.add(`member:${e.member}`); set.add(`process:${e.process}`); }
    }
    if (kind === "dept") for (const m of model.membersOf(id)) set.add(`member:${m.id}`);
    return set;
  }, [focus, scene.edges, model]);
  const lit = (key: string) => !related || related.has(key);

  const handlers = (key: string) => ({
    onClick: (e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onSelect(key); },
    onPointerOver: (e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); setHover(key); document.body.style.cursor = "pointer"; },
    onPointerOut: () => { setHover(null); document.body.style.cursor = ""; },
  });

  const edgeColor = (r: RoleKey) => (r === "owner" ? palette.primary : r === "executor" ? palette.cyan : r === "approver" ? palette.violet : palette.muted);
  const label = (text: string, sub: string | undefined, strong: boolean) => (
    <div
      style={{ color: palette.text, opacity: strong ? 1 : 0.55 }}
      className="pointer-events-none whitespace-nowrap rounded-md px-1.5 py-0.5 text-center text-[11px] leading-tight"
    >
      <div className={strong ? "font-semibold" : undefined}>{text}</div>
      {sub && strong && <div className="text-[10px] opacity-70">{sub}</div>}
    </div>
  );

  return (
    <Canvas
      camera={{ position: [0, scene.PR * 1.35, scene.PR * 1.75], fov: 45 }}
      dpr={[1, 2]}
      onPointerMissed={() => onSelect(null)}
      style={{ background: palette.background }}
    >
      <ambientLight intensity={0.75} />
      <directionalLight position={[10, 20, 10]} intensity={1.1} />
      <gridHelper args={[scene.R * 5, 40, palette.grid, palette.grid]} position={[0, -0.01, 0]} />

      {/* kompaniya */}
      <mesh position={[0, 1, 0]} {...handlers("company:0")}>
        <icosahedronGeometry args={[0.9, 0]} />
        <meshStandardMaterial color={palette.primary} flatShading emissive={palette.primary} emissiveIntensity={0.25} />
        <Html center position={[0, 1.4, 0]}>{label(model.state.meta.company, undefined, true)}</Html>
      </mesh>

      {/* bo'limlar */}
      {scene.deptNodes.map((d) => (
        <group key={d.key} position={d.pos}>
          <Line points={[[0, 0, 0], [-d.pos[0], 0.99, -d.pos[2]]]} color={palette.grid} lineWidth={1} transparent opacity={lit(d.key) ? 0.9 : 0.2} />
          <mesh rotation={[-Math.PI / 2, 0, 0]} {...handlers(d.key)}>
            <ringGeometry args={[d.radius - 0.08, d.radius, 64]} />
            <meshBasicMaterial color={selected === d.key ? palette.primary : palette.muted} transparent opacity={lit(d.key) ? 0.9 : 0.25} />
          </mesh>
          <Html center position={[0, 0.05, d.radius + 0.6]}>
            <div style={{ color: palette.text }} className="pointer-events-none whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.14em] opacity-70">{d.label}</div>
          </Html>
        </group>
      ))}

      {/* bog'lanishlar: rol — chiziq uslubi (uzluksiz/uzuq) */}
      {scene.edges.map((e) => {
        const on = lit(`member:${e.member}`) && lit(`process:${e.process}`);
        const dash = ROLE_DASH[e.role];
        return (
          <Line
            key={`${e.member}-${e.process}`}
            points={[e.from, [(e.from[0] + e.to[0]) / 2, Math.max(e.from[1], e.to[1]) + 1.2, (e.from[2] + e.to[2]) / 2], e.to]}
            color={edgeColor(e.role)}
            lineWidth={on && related ? 2 : 1}
            transparent
            opacity={on ? (related ? 0.95 : 0.45) : 0.05}
            dashed={!!dash}
            dashSize={0.35}
            gapSize={0.25}
          />
        );
      })}

      {/* xodimlar */}
      {scene.memberNodes.map((m) => {
        const on = lit(m.key);
        const isSel = selected === m.key;
        const w = model.workload.find((x) => x.member.id === m.id);
        return (
          <mesh key={m.key} position={m.pos} {...handlers(m.key)}>
            <sphereGeometry args={[isSel ? 0.48 : 0.36, 32, 32]} />
            <meshStandardMaterial
              color={w?.excessive ? palette.warning : palette.cyan}
              emissive={isSel ? palette.primary : "#000000"}
              emissiveIntensity={isSel ? 0.6 : 0}
              transparent
              opacity={on ? 1 : 0.2}
            />
            <Html center position={[0, 0.75, 0]}>{label(m.label, m.sub, on && (!!related || isSel))}</Html>
          </mesh>
        );
      })}

      {/* jarayonlar */}
      {scene.processNodes.map((p) => {
        const on = lit(p.key);
        const level = model.level(p.id);
        const isSel = selected === p.key;
        return (
          <mesh key={p.key} position={p.pos} rotation={[0.4, 0.6, 0]} {...handlers(p.key)}>
            <boxGeometry args={isSel ? [0.62, 0.62, 0.62] : [0.42, 0.42, 0.42]} />
            <meshStandardMaterial
              color={level === "danger" ? palette.danger : level === "warn" ? palette.warning : palette.violet}
              transparent
              opacity={on ? 1 : 0.15}
            />
            {(isSel || hover === p.key || (related && on)) && <Html center position={[0, 0.6, 0]}>{label(p.label, p.sub, true)}</Html>}
          </mesh>
        );
      })}

      <OrbitControls makeDefault enableDamping autoRotate={!selected && !hover} autoRotateSpeed={0.35} maxPolarAngle={Math.PI / 2.05} minDistance={4} maxDistance={scene.PR * 5} />
    </Canvas>
  );
}
