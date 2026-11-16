"use client";

import { ContactShadows, Float, Html, OrbitControls, QuadraticBezierLine } from "@react-three/drei";
import { Canvas, useFrame, type ThreeEvent } from "@react-three/fiber";
import { useMemo, useRef, useState } from "react";

import type { RoleKey, Zone, ZoneIcon } from "@/lib/api/types";
import { ROLE_DASH, type Model } from "@/lib/model";

import { PersonIcon, PlatformIcon, ProcessIcon, TeamIcon, TowerIcon } from "./icons3d";

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
  platform: string;
  head: string;
}

interface SceneEdge { member: number; process: number; role: RoleKey; from: Vec3; to: Vec3 }
interface ZoneIsland { key: string; zone: Zone | null; pos: Vec3; radius: number; processes: number[] }

const NO_ZONE: Pick<Zone, "icon" | "color" | "name"> = { icon: "box", color: "#64748B", name: "—" };

/**
 * Joylashuv: kompaniya minorasi markazda; bo'limlar ichki halqada (maydonchada xodimlar);
 * jarayonlar tashqi halqada zona "orollari"ga guruhlangan — orol bog'langan xodimlar tomonida turadi.
 */
function layout3d(model: Model, inScope: (deptId: number) => boolean, hidden: RoleKey[]) {
  const depts = [...model.state.departments.map((d) => d.id), 0].filter((d) => model.membersOf(d).length && inScope(d));
  const R = Math.max(6, depts.length * 2.6);
  const memberPos = new Map<number, Vec3>();
  const deptNodes = depts.map((d, i) => {
    const a = (i / depts.length) * Math.PI * 2 + Math.PI / 4;
    const c: Vec3 = [R * Math.cos(a), 0, R * Math.sin(a)];
    const ms = model.membersOf(d);
    const ring = ms.length > 1 ? 0.75 + ms.length * 0.22 : 0;
    ms.forEach((m, j) => {
      const b = a + Math.PI + (j / ms.length) * Math.PI * 2;
      memberPos.set(m.id, [c[0] + ring * Math.cos(b), 0, c[2] + ring * Math.sin(b)]);
    });
    return { key: `dept:${d}`, id: d, pos: c, radius: ring + 1.0, label: model.dept.get(d)?.name ?? "—", members: ms };
  });

  // jarayonlar: bog'langan xodimlar bo'lgan, zonalar bo'yicha
  const procs = model.state.processes.filter((p) => (model.linksOfProcess.get(p.id) ?? []).some((l) => memberPos.has(l.memberId)));
  const byZone = new Map<number | null, number[]>();
  for (const p of procs) byZone.set(p.zone, [...(byZone.get(p.zone) ?? []), p.id]);
  const angleOf = (pids: number[]) => {
    let x = 0;
    let z = 0;
    for (const pid of pids) for (const l of model.linksOfProcess.get(pid) ?? []) {
      const mp = memberPos.get(l.memberId);
      if (!mp) continue;
      const w = l.roles.has("owner") ? 3 : 1;
      x += mp[0] * w;
      z += mp[2] * w;
    }
    return Math.atan2(z, x);
  };
  const zonesSorted = [...byZone.entries()].map(([zid, pids]) => ({ zid, pids, angle: angleOf(pids) })).sort((a, b) => a.angle - b.angle);
  const radii = zonesSorted.map(({ pids }) => 1.4 + Math.sqrt(pids.length) * 1.15);
  const circumference = radii.reduce((s, r) => s + 2 * r + 1.6, 0);
  const PR = Math.max(R + 7, circumference / (2 * Math.PI));
  const processPos = new Map<number, Vec3>();
  const islands: ZoneIsland[] = [];
  let acc = zonesSorted[0]?.angle ?? 0;
  zonesSorted.forEach(({ zid, pids }, i) => {
    const r = radii[i];
    const span = (2 * r + 1.6) / PR;
    const a = acc + span / 2;
    acc += span;
    const c: Vec3 = [PR * Math.cos(a), 0, PR * Math.sin(a)];
    islands.push({ key: `zone:${zid ?? 0}`, zone: zid ? model.zone.get(zid) ?? null : null, pos: c, radius: r, processes: pids });
    // orol ichida: markazdan spiral bo'ylab
    pids.forEach((pid, k) => {
      if (k === 0 && pids.length === 1) return processPos.set(pid, [c[0], 0.25, c[2]]);
      const t = k + 0.6;
      const rr = Math.min(r - 0.6, 0.85 * Math.sqrt(t));
      const ang = t * 2.4;
      processPos.set(pid, [c[0] + rr * Math.cos(ang), 0.25, c[2] + rr * Math.sin(ang)]);
    });
  });

  const edges: SceneEdge[] = [];
  for (const [pid, to] of processPos) {
    for (const l of model.linksOfProcess.get(pid) ?? []) {
      const from = memberPos.get(l.memberId);
      if (!from) continue;
      const role = l.roles.has("owner") && !hidden.includes("owner") ? "owner" : [...l.roles].find((r) => !hidden.includes(r));
      if (!role) continue;
      edges.push({ member: l.memberId, process: pid, role, from: [from[0], 0.6, from[2]], to: [to[0], to[1] + 0.5, to[2]] });
    }
  }
  return { R, PR, deptNodes, memberPos, processPos, islands, edges };
}

/** Bog'lanish: kavisli chiziq; ajratilganda oqim harakatlanadi. */
function Edge({ e, color, lit, strong }: { e: SceneEdge; color: string; lit: boolean; strong: boolean }) {
  const ref = useRef<{ material: { dashOffset: number } } | null>(null);
  useFrame((_, dt) => {
    if (strong && ref.current) ref.current.material.dashOffset -= dt * 1.2;
  });
  const dist = Math.hypot(e.to[0] - e.from[0], e.to[2] - e.from[2]);
  const mid: Vec3 = [(e.from[0] + e.to[0]) / 2, 1.2 + dist * 0.18, (e.from[2] + e.to[2]) / 2];
  const dash = ROLE_DASH[e.role];
  return (
    <QuadraticBezierLine
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      ref={ref as any}
      start={e.from} end={e.to} mid={mid}
      color={color} lineWidth={strong ? 2.4 : 1.1} transparent
      opacity={lit ? (strong ? 1 : 0.4) : 0.05}
      dashed={strong || !!dash} dashSize={strong ? 0.5 : 0.35} gapSize={strong ? 0.3 : 0.25}
    />
  );
}

function Label({ text, sub, color, strong, accent, hidden }: { text: string; sub?: string; color: string; strong?: boolean; accent?: string; hidden?: boolean }) {
  // yorliq doim render qilinadi (Html ildizini qayta-qayta yaratmaslik uchun), keraksizda yashiriladi
  return (
    <div
      aria-hidden={hidden}
      className="pointer-events-none whitespace-nowrap rounded-lg border px-2 py-0.5 text-center text-[11px] leading-tight shadow-sm backdrop-blur-md"
      style={{
        color, opacity: hidden ? 0 : strong === false ? 0.55 : 1, transition: "opacity .15s",
        background: "color-mix(in srgb, var(--card) 72%, transparent)",
        borderColor: accent ? `color-mix(in srgb, ${accent} 55%, transparent)` : "var(--border)",
      }}
    >
      <div className={strong ? "font-semibold" : "font-medium"}>{text}</div>
      {sub && <div className="text-[10px] opacity-70">{sub}</div>}
    </div>
  );
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
  const scene = useMemo(() => layout3d(model, (d) => !scope || d === scope, hiddenRoles), [model, scope, hiddenRoles]);

  // tanlangan/ustidagi tugunga bog'liq hamma narsa yorqin, qolgani xira
  const focus = hover ?? selected;
  const related = useMemo(() => {
    if (!focus || focus === "company:0") return null;
    const [kind, raw] = focus.split(":");
    const id = Number(raw);
    const set = new Set<string>([focus]);
    const zoneProcs = kind === "zone" ? new Set(scene.islands.find((i) => i.key === focus)?.processes ?? []) : null;
    for (const e of scene.edges) {
      const m = model.member.get(e.member);
      const hit = (kind === "member" && e.member === id) || (kind === "process" && e.process === id)
        || (kind === "dept" && !!m && model.deptOf(m) === id) || (!!zoneProcs && zoneProcs.has(e.process));
      if (hit) {
        set.add(`member:${e.member}`);
        set.add(`process:${e.process}`);
      }
    }
    if (kind === "dept") for (const m of model.membersOf(id)) set.add(`member:${m.id}`);
    if (zoneProcs) for (const pid of zoneProcs) set.add(`process:${pid}`);
    for (const isl of scene.islands) if (isl.processes.some((pid) => set.has(`process:${pid}`))) set.add(isl.key);
    return set;
  }, [focus, scene, model]);
  const lit = (key: string) => !related || related.has(key);

  const handlers = (key: string) => ({
    onClick: (e: ThreeEvent<MouseEvent>) => { e.stopPropagation(); onSelect(key); },
    onPointerOver: (e: ThreeEvent<PointerEvent>) => { e.stopPropagation(); setHover(key); document.body.style.cursor = "pointer"; },
    onPointerOut: () => { setHover(null); document.body.style.cursor = ""; },
  });
  const roleColor = (r: RoleKey) => (r === "owner" ? palette.primary : r === "executor" ? palette.cyan : r === "approver" ? palette.violet : palette.muted);

  return (
    <Canvas
      shadows
      camera={{ position: [0, scene.PR * 0.72, scene.PR * 1.18], fov: 45 }}
      dpr={[1, 2]}
      onPointerMissed={() => onSelect(null)}
      style={{ background: palette.background }}
    >
      <fog attach="fog" args={[palette.background, scene.PR * 2.2, scene.PR * 4.5]} />
      <hemisphereLight args={["#ffffff", palette.grid, 0.9]} />
      <ambientLight intensity={0.35} />
      <directionalLight position={[12, 24, 10]} intensity={1.4} castShadow shadow-mapSize={[2048, 2048]}
        shadow-camera-left={-scene.PR * 1.4} shadow-camera-right={scene.PR * 1.4} shadow-camera-top={scene.PR * 1.4} shadow-camera-bottom={-scene.PR * 1.4} />
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.2, 0]} receiveShadow>
        <circleGeometry args={[scene.PR * 2.2, 96]} />
        <meshStandardMaterial color={palette.background} roughness={1} />
      </mesh>
      <gridHelper args={[scene.PR * 4, 60, palette.grid, palette.grid]} position={[0, -0.19, 0]} />
      <ContactShadows position={[0, -0.18, 0]} scale={scene.PR * 3} opacity={0.35} blur={2.4} far={5} frames={1} />

      {/* kompaniya minorasi */}
      <group {...handlers("company:0")} scale={selected === "company:0" ? 1.08 : 1}>
        <TowerIcon color={palette.platform} accent={palette.primary} />
        <Html center position={[0, 3.8, 0]}><Label text={model.state.meta.company} color={palette.text} strong accent={palette.primary} /></Html>
      </group>

      {/* bo'limlar va xodimlar */}
      {scene.deptNodes.map((d) => (
        <group key={d.key}>
          <group position={d.pos} {...handlers(d.key)}>
            <PlatformIcon radius={d.radius} color={palette.platform} rim={selected === d.key ? palette.primary : palette.muted} opacity={lit(d.key) ? 1 : 0.35} />
            <Html center position={[0, 0.05, d.radius + 0.55]}>
              <div style={{ color: palette.text }} className="pointer-events-none whitespace-nowrap text-[10px] font-semibold uppercase tracking-[0.16em] opacity-75">{d.label}</div>
            </Html>
          </group>
          {d.members.map((m) => {
            const key = `member:${m.id}`;
            const pos = scene.memberPos.get(m.id)!;
            const on = lit(key);
            const isSel = selected === key;
            const w = model.workload.find((x) => x.member.id === m.id);
            const color = w?.excessive ? palette.warning : m.is_team ? palette.violet : palette.cyan;
            const look = { color, head: palette.head, opacity: on ? 1 : 0.22, emissive: isSel || hover === key ? 0.45 : 0.05 };
            return (
              <group key={key} position={pos} scale={isSel ? 1.6 : 1.3} {...handlers(key)}>
                {m.is_team ? <TeamIcon {...look} /> : <PersonIcon {...look} />}
                <Html center position={[0, 1.05, 0]}>
                  <Label text={m.name} sub={on && (isSel || !!related) ? m.role : undefined} color={palette.text} strong={on} accent={isSel ? palette.primary : undefined} />
                </Html>
              </group>
            );
          })}
        </group>
      ))}

      {/* zona orollari va jarayonlar */}
      {scene.islands.map((isl) => {
        const z = isl.zone ?? NO_ZONE;
        const on = lit(isl.key);
        return (
          <group key={isl.key}>
            <group position={isl.pos} {...handlers(isl.key)}>
              <mesh position={[0, -0.06, 0]} receiveShadow>
                <cylinderGeometry args={[isl.radius, isl.radius * 1.04, 0.12, 48]} />
                <meshStandardMaterial color={z.color} transparent opacity={on ? 0.16 : 0.05} roughness={0.8} />
              </mesh>
              <mesh position={[0, 0.002, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                <ringGeometry args={[isl.radius - 0.05, isl.radius, 64]} />
                <meshBasicMaterial color={z.color} transparent opacity={on ? 0.85 : 0.2} />
              </mesh>
              <Html center position={[0, 0.05, isl.radius + 0.5]}>
                <div className="pointer-events-none flex items-center gap-1.5 whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold shadow-sm"
                  style={{ color: "#fff", background: z.color, opacity: on ? 1 : 0.4 }}>
                  {z.name} · {isl.processes.length}
                </div>
              </Html>
            </group>
            {isl.processes.map((pid) => {
              const key = `process:${pid}`;
              const p = model.process.get(pid);
              const pos = scene.processPos.get(pid);
              if (!p || !pos) return null;
              const pOn = lit(key);
              const isSel = selected === key;
              const level = model.level(pid);
              return (
                <group key={key} position={pos} {...handlers(key)}>
                  <Float speed={1.4} rotationIntensity={0.15} floatIntensity={0.35} floatingRange={[0, 0.12]}>
                    <group scale={isSel ? 2.1 : hover === key ? 1.85 : 1.6}>
                      <ProcessIcon icon={(z.icon as ZoneIcon) ?? "box"} color={z.color} opacity={pOn ? 1 : 0.15} emissive={isSel ? 0.5 : 0} />
                    </group>
                  </Float>
                  {(level || isSel) && (
                    <mesh position={[0, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
                      <ringGeometry args={[0.55, 0.66, 40]} />
                      <meshBasicMaterial color={isSel ? palette.primary : level === "danger" ? palette.danger : palette.warning} transparent opacity={pOn ? 0.95 : 0.2} />
                    </mesh>
                  )}
                  <Html center position={[0, 1.45, 0]}>
                    <Label
                      text={p.name} sub={(model.tasksOf.get(pid) ?? []).length + " · " + (model.systemName(p) || z.name)} color={palette.text} strong accent={z.color}
                      hidden={!(isSel || hover === key || (!!related && pOn && related.size < 30))}
                    />
                  </Html>
                </group>
              );
            })}
          </group>
        );
      })}

      {/* bog'lanishlar: rol — rang va chiziq uslubi */}
      {scene.edges.map((e) => {
        const on = lit(`member:${e.member}`) && lit(`process:${e.process}`);
        return <Edge key={`${e.member}-${e.process}`} e={e} color={roleColor(e.role)} lit={on} strong={on && !!related} />;
      })}

      <OrbitControls makeDefault enableDamping autoRotate={!selected && !hover} autoRotateSpeed={0.3}
        maxPolarAngle={Math.PI / 2.1} minDistance={4} maxDistance={scene.PR * 4.5} target={[0, 0.8, 0]} />
    </Canvas>
  );
}
