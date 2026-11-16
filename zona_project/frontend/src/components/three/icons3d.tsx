"use client";

/**
 * 3D ikonkalar: tugunning haqiqiy ma'nosini ko'rsatadi.
 * Xodim — odam qiyofasi, jamoa — odamlar guruhi, bo'lim — olti burchakli maydoncha, kompaniya — shisha minora,
 * jarayon — zonasiga mos buyum (yuk mashinasi, smartfon, ma'lumotlar bazasi, zanjir, diagramma, server, qalqon).
 */
import { RoundedBox } from "@react-three/drei";
import { useMemo } from "react";
import * as THREE from "three";

import type { ZoneIcon } from "@/lib/api/types";

interface Look {
  color: string;
  opacity?: number;
  emissive?: number;
}

function Mat({ color, opacity = 1, emissive = 0, metal = 0.15, rough = 0.45 }: Look & { metal?: number; rough?: number }) {
  return (
    <meshStandardMaterial
      color={color} metalness={metal} roughness={rough} transparent={opacity < 1} opacity={opacity}
      emissive={color} emissiveIntensity={emissive}
    />
  );
}

/** Odam: bosh, gavda (kapsula) va taglik. */
export function PersonIcon({ color, head = "#E8EDF5", opacity = 1, emissive = 0 }: Look & { head?: string }) {
  return (
    <group>
      <mesh position={[0, 0.03, 0]} receiveShadow>
        <cylinderGeometry args={[0.32, 0.34, 0.06, 32]} />
        <Mat color={color} opacity={opacity * 0.55} emissive={emissive * 0.5} />
      </mesh>
      <mesh position={[0, 0.34, 0]} castShadow>
        <capsuleGeometry args={[0.17, 0.26, 8, 20]} />
        <Mat color={color} opacity={opacity} emissive={emissive} />
      </mesh>
      <mesh position={[0, 0.75, 0]} castShadow>
        <sphereGeometry args={[0.15, 32, 32]} />
        <Mat color={head} opacity={opacity} emissive={emissive * 0.4} rough={0.35} />
      </mesh>
    </group>
  );
}

/** Jamoa: uchta odam, o'rtadagisi oldinda. */
export function TeamIcon(props: Look & { head?: string }) {
  return (
    <group>
      <group position={[-0.3, 0, -0.12]} scale={0.78}><PersonIcon {...props} /></group>
      <group position={[0.3, 0, -0.12]} scale={0.78}><PersonIcon {...props} /></group>
      <group position={[0, 0, 0.14]}><PersonIcon {...props} /></group>
    </group>
  );
}

/** Kompaniya: shisha minora, derazalar va yonib turgan cho'qqi. */
export function TowerIcon({ color, accent }: { color: string; accent: string }) {
  return (
    <group>
      <RoundedBox args={[2.1, 0.25, 2.1]} radius={0.06} position={[0, 0.125, 0]} receiveShadow castShadow>
        <Mat color={color} opacity={0.9} metal={0.4} rough={0.3} />
      </RoundedBox>
      <RoundedBox args={[1.15, 2.4, 1.15]} radius={0.08} position={[0, 1.45, 0]} castShadow>
        <meshPhysicalMaterial color={accent} metalness={0.35} roughness={0.12} transmission={0.25} transparent opacity={0.92} clearcoat={1} />
      </RoundedBox>
      {Array.from({ length: 7 }, (_, i) => (
        <mesh key={i} position={[0, 0.55 + i * 0.3, 0.58]}>
          <boxGeometry args={[0.9, 0.06, 0.01]} />
          <meshBasicMaterial color="#DDEBFF" transparent opacity={0.75} />
        </mesh>
      ))}
      <RoundedBox args={[0.7, 0.5, 0.7]} radius={0.06} position={[1.0, 0.5, 0.3]} castShadow>
        <Mat color={accent} opacity={0.85} metal={0.3} rough={0.25} />
      </RoundedBox>
      <mesh position={[0, 2.95, 0]}><cylinderGeometry args={[0.03, 0.03, 0.6, 8]} /><Mat color={color} /></mesh>
      <mesh position={[0, 3.3, 0]}><sphereGeometry args={[0.11, 24, 24]} /><meshBasicMaterial color={accent} /></mesh>
      <pointLight position={[0, 3.3, 0]} color={accent} intensity={6} distance={6} />
    </group>
  );
}

/** Bo'lim: olti burchakli maydoncha (ustida xodimlar turadi). */
export function PlatformIcon({ radius, color, rim, opacity = 1 }: { radius: number; color: string; rim: string; opacity?: number }) {
  return (
    <group>
      <mesh position={[0, -0.09, 0]} receiveShadow>
        <cylinderGeometry args={[radius, radius * 1.05, 0.18, 6]} />
        <Mat color={color} opacity={0.9 * opacity} metal={0.2} rough={0.6} />
      </mesh>
      <mesh position={[0, 0.005, 0]} rotation={[-Math.PI / 2, 0, Math.PI / 6]}>
        <ringGeometry args={[radius * 0.96, radius, 6]} />
        <meshBasicMaterial color={rim} transparent opacity={0.9 * opacity} />
      </mesh>
    </group>
  );
}

function Truck({ color, opacity, emissive }: Look) {
  return (
    <group position={[0, 0.02, 0]}>
      <RoundedBox args={[0.6, 0.36, 0.34]} radius={0.04} position={[-0.1, 0.3, 0]} castShadow><Mat color={color} opacity={opacity} emissive={emissive} /></RoundedBox>
      <RoundedBox args={[0.24, 0.27, 0.32]} radius={0.04} position={[0.32, 0.25, 0]} castShadow><Mat color="#E8EDF5" opacity={opacity} /></RoundedBox>
      <mesh position={[0.4, 0.3, 0]}><boxGeometry args={[0.08, 0.1, 0.28]} /><meshStandardMaterial color="#1E293B" /></mesh>
      {[[-0.25, 0.17], [-0.25, -0.17], [0.3, 0.17], [0.3, -0.17]].map(([x, z]) => (
        <mesh key={`${x}${z}`} position={[x, 0.08, z]} rotation={[Math.PI / 2, 0, 0]} castShadow>
          <cylinderGeometry args={[0.08, 0.08, 0.06, 20]} /><meshStandardMaterial color="#1E293B" roughness={0.8} />
        </mesh>
      ))}
    </group>
  );
}

function Phone({ color, opacity, emissive }: Look) {
  return (
    <group position={[0, 0.38, 0]} rotation={[-0.15, 0.35, 0]}>
      <RoundedBox args={[0.36, 0.66, 0.06]} radius={0.05} castShadow><Mat color="#1E293B" opacity={opacity} metal={0.5} rough={0.25} /></RoundedBox>
      <mesh position={[0, 0.01, 0.032]}><planeGeometry args={[0.3, 0.54]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.6 + (emissive ?? 0)} transparent opacity={opacity} /></mesh>
      {[0.12, 0, -0.12].map((y) => (
        <mesh key={y} position={[0, y, 0.034]}><planeGeometry args={[0.2, 0.05]} /><meshBasicMaterial color="#FFFFFF" transparent opacity={0.65 * (opacity ?? 1)} /></mesh>
      ))}
    </group>
  );
}

function Database({ color, opacity, emissive }: Look) {
  return (
    <group>
      {[0.1, 0.27, 0.44].map((y) => (
        <group key={y} position={[0, y, 0]}>
          <mesh castShadow><cylinderGeometry args={[0.24, 0.24, 0.13, 32]} /><Mat color={color} opacity={opacity} emissive={emissive} metal={0.3} rough={0.35} /></mesh>
          <mesh position={[0, 0.066, 0]} rotation={[-Math.PI / 2, 0, 0]}><ringGeometry args={[0.18, 0.24, 32]} /><meshBasicMaterial color="#FFFFFF" transparent opacity={0.35} /></mesh>
        </group>
      ))}
    </group>
  );
}

function Link3d({ color, opacity, emissive }: Look) {
  return (
    <group position={[0, 0.32, 0]}>
      <mesh position={[-0.12, 0, 0]} castShadow><torusGeometry args={[0.16, 0.05, 16, 40]} /><Mat color={color} opacity={opacity} emissive={emissive} metal={0.6} rough={0.25} /></mesh>
      <mesh position={[0.12, 0, 0]} rotation={[0, Math.PI / 2, 0]} castShadow><torusGeometry args={[0.16, 0.05, 16, 40]} /><Mat color="#E8EDF5" opacity={opacity} metal={0.6} rough={0.25} /></mesh>
    </group>
  );
}

function Chart({ color, opacity, emissive }: Look) {
  return (
    <group>
      <RoundedBox args={[0.6, 0.05, 0.3]} radius={0.02} position={[0, 0.025, 0]} receiveShadow><Mat color="#94A3B8" opacity={opacity} /></RoundedBox>
      {[[-0.18, 0.22], [0, 0.4], [0.18, 0.58]].map(([x, h]) => (
        <RoundedBox key={x} args={[0.13, h, 0.13]} radius={0.025} position={[x, 0.05 + h / 2, 0]} castShadow>
          <Mat color={color} opacity={opacity} emissive={emissive} />
        </RoundedBox>
      ))}
    </group>
  );
}

function ServerRack({ color, opacity, emissive }: Look) {
  return (
    <group position={[0, 0.33, 0]}>
      <RoundedBox args={[0.4, 0.62, 0.34]} radius={0.04} castShadow><Mat color="#1E293B" opacity={opacity} metal={0.5} rough={0.3} /></RoundedBox>
      {[0.18, 0, -0.18].map((y) => (
        <group key={y} position={[0, y, 0.172]}>
          <mesh><planeGeometry args={[0.32, 0.12]} /><meshStandardMaterial color={color} emissive={color} emissiveIntensity={0.35 + (emissive ?? 0)} transparent opacity={opacity} /></mesh>
          <mesh position={[0.11, 0, 0.002]}><circleGeometry args={[0.018, 12]} /><meshBasicMaterial color="#22C55E" /></mesh>
          <mesh position={[0.06, 0, 0.002]}><circleGeometry args={[0.018, 12]} /><meshBasicMaterial color="#F8FAFC" /></mesh>
        </group>
      ))}
    </group>
  );
}

function Shield({ color, opacity, emissive }: Look) {
  const geom = useMemo(() => {
    const s = new THREE.Shape();
    s.moveTo(0, 0.34);
    s.bezierCurveTo(0.12, 0.3, 0.22, 0.29, 0.26, 0.28);
    s.bezierCurveTo(0.27, 0.05, 0.2, -0.14, 0, -0.3);
    s.bezierCurveTo(-0.2, -0.14, -0.27, 0.05, -0.26, 0.28);
    s.bezierCurveTo(-0.22, 0.29, -0.12, 0.3, 0, 0.34);
    const g = new THREE.ExtrudeGeometry(s, { depth: 0.08, bevelEnabled: true, bevelThickness: 0.025, bevelSize: 0.02, bevelSegments: 4 });
    g.center();
    return g;
  }, []);
  return (
    <group position={[0, 0.38, 0]} rotation={[0, 0.35, 0]}>
      <mesh geometry={geom} castShadow><Mat color={color} opacity={opacity} emissive={emissive} metal={0.4} rough={0.3} /></mesh>
      <mesh position={[0, 0.02, 0.07]} rotation={[0, 0, Math.PI / 4]}>
        <boxGeometry args={[0.05, 0.16, 0.02]} /><meshBasicMaterial color="#FFFFFF" />
      </mesh>
      <mesh position={[0.06, 0.06, 0.07]} rotation={[0, 0, -Math.PI / 4]}>
        <boxGeometry args={[0.05, 0.26, 0.02]} /><meshBasicMaterial color="#FFFFFF" />
      </mesh>
    </group>
  );
}

function Cube({ color, opacity, emissive }: Look) {
  return <RoundedBox args={[0.42, 0.42, 0.42]} radius={0.06} position={[0, 0.25, 0]} rotation={[0.3, 0.5, 0]} castShadow><Mat color={color} opacity={opacity} emissive={emissive} /></RoundedBox>;
}

/** Jarayon: zonasiga mos 3D buyum. */
export function ProcessIcon({ icon, ...look }: Look & { icon: ZoneIcon }) {
  switch (icon) {
    case "truck": return <Truck {...look} />;
    case "smartphone": return <Phone {...look} />;
    case "database": return <Database {...look} />;
    case "plug": return <Link3d {...look} />;
    case "chart": return <Chart {...look} />;
    case "server": return <ServerRack {...look} />;
    case "shield": return <Shield {...look} />;
    case "users": return <TeamIcon {...look} />;
    default: return <Cube {...look} />;
  }
}
