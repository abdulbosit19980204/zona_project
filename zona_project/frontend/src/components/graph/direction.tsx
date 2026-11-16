"use client";

import { ArrowDownFromLine, ArrowRightFromLine } from "lucide-react";
import { useTranslations } from "next-intl";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useUI, type MapDir } from "@/stores/ui";

interface Placed {
  id: string;
  position: { x: number; y: number };
  width?: number;
  height?: number;
  data: Record<string, unknown>;
}

const GAP_X = 32; // yonma-yon kichik daraxtlar orasidagi masofa
const GAP_Y = 64; // ota tugun va bolalar qatori orasidagi masofa
const STACK_GAP = 12; // ustun bo'lib tizilgan barglar orasidagi masofa
const INDENT = 20; // barglar ustuni ota tugun markazidan qancha o'ngda boshlanadi

/**
 * Vertikal (yuqoridan pastga) daraxt joylashuvi.
 * parents: tugun -> ota tugun (tuzilma bog'lanishlari). Bolalarining hammasi barg bo'lgan tugun ostida
 * barglar ustun bo'lib tiziladi (data.stacked = true — ular chap tomondan ulanadi), qolganlari
 * yonma-yon joylashib, ota tugun ular ustida markazlanadi. LR rejimida tugunlar o'zgarishsiz qaytadi.
 */
export function orientTree<N extends Placed>(nodes: N[], dir: MapDir, parents: Map<string, string>): N[] {
  if (dir === "LR" || !nodes.length) return nodes;
  const byId = new Map(nodes.map((n) => [n.id, n]));
  const w = (id: string) => byId.get(id)?.width ?? 200;
  const h = (id: string) => byId.get(id)?.height ?? 60;
  const order = (id: string) => byId.get(id)!.position.y; // gorizontal tartib saqlanadi
  const kids = new Map<string, string[]>();
  const roots: string[] = [];
  for (const n of nodes) {
    const p = parents.get(n.id);
    if (p && byId.has(p) && p !== n.id) kids.set(p, [...(kids.get(p) ?? []), n.id]);
    else roots.push(n.id);
  }
  for (const list of kids.values()) list.sort((a, b) => order(a) - order(b));
  roots.sort((a, b) => order(a) - order(b));

  const childrenOf = (id: string) => kids.get(id) ?? [];
  const stacked = (id: string) => childrenOf(id).length > 0 && childrenOf(id).every((c) => !childrenOf(c).length);
  const widths = new Map<string, number>();
  const visiting = new Set<string>();
  const measure = (id: string): number => {
    if (widths.has(id)) return widths.get(id)!;
    if (visiting.has(id)) return w(id); // halqadan himoya
    visiting.add(id);
    const cs = childrenOf(id);
    let width = w(id);
    if (cs.length && stacked(id)) width = Math.max(width, w(id) / 2 + INDENT + Math.max(...cs.map(w)));
    else if (cs.length) width = Math.max(width, cs.reduce((s, c) => s + measure(c), 0) + GAP_X * (cs.length - 1));
    widths.set(id, width);
    return width;
  };

  const pos = new Map<string, { x: number; y: number; stacked?: boolean }>();
  const place = (id: string, left: number, top: number) => {
    const cs = childrenOf(id);
    const width = measure(id);
    if (cs.length && stacked(id)) {
      const x = left + Math.max(0, (width - (w(id) / 2 + INDENT + Math.max(...cs.map(w)))) / 2);
      pos.set(id, { x, y: top });
      let y = top + h(id) + GAP_Y / 2;
      for (const c of cs) {
        pos.set(c, { x: x + w(id) / 2 + INDENT, y, stacked: true });
        y += h(c) + STACK_GAP;
      }
      return;
    }
    if (!cs.length) {
      pos.set(id, { x: left + (width - w(id)) / 2, y: top });
      return;
    }
    const inner = cs.reduce((s, c) => s + measure(c), 0) + GAP_X * (cs.length - 1);
    let x = left + (width - inner) / 2;
    const childTop = top + h(id) + GAP_Y;
    for (const c of cs) {
      place(c, x, childTop);
      x += measure(c) + GAP_X;
    }
    // ota tugun birinchi va oxirgi bola markazlari o'rtasida
    const first = pos.get(cs[0])!;
    const last = pos.get(cs[cs.length - 1])!;
    const mid = (first.x + w(cs[0]) / 2 + last.x + w(cs[cs.length - 1]) / 2) / 2;
    pos.set(id, { x: mid - w(id) / 2, y: top });
  };
  let left = 0;
  for (const r of roots) {
    place(r, left, 0);
    left += measure(r) + GAP_X * 2;
  }
  return nodes.map((n) => {
    const p = pos.get(n.id);
    if (!p) return n;
    return { ...n, position: { x: p.x, y: p.y }, data: { ...n.data, stacked: !!p.stacked } };
  });
}

/** Xarita yo'nalishini almashtirish: gorizontal (chapdan o'ngga) / vertikal (yuqoridan pastga). */
export function DirectionToggle({ className }: { className?: string }) {
  const t = useTranslations("common.mapDir");
  const dir = useUI((s) => s.mapDir);
  const setDir = useUI((s) => s.setMapDir);
  const next: MapDir = dir === "LR" ? "TB" : "LR";
  const label = t(next === "TB" ? "toVertical" : "toHorizontal");
  return (
    <Button variant="outline" size="icon" className={cn("pointer-events-auto", className)} onClick={() => setDir(next)} aria-label={label} title={label}>
      {dir === "LR" ? <ArrowDownFromLine className="size-4" /> : <ArrowRightFromLine className="size-4" />}
    </Button>
  );
}
