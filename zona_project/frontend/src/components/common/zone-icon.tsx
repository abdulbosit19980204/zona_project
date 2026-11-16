import { Box, ChartColumn, Database, Plug, Server, ShieldCheck, Smartphone, Truck, Users, type LucideIcon } from "lucide-react";

import type { Zone, ZoneIcon as ZoneIconKey } from "@/lib/api/types";
import { cn } from "@/lib/utils";

export const ZONE_ICONS: Record<ZoneIconKey, LucideIcon> = {
  truck: Truck, smartphone: Smartphone, database: Database, plug: Plug, chart: ChartColumn,
  server: Server, shield: ShieldCheck, users: Users, box: Box,
};

/** Zona belgisi: rangli plitka ichida ikonka. */
export function ZoneIcon({ zone, size = 36, className }: { zone?: Pick<Zone, "icon" | "color">; size?: number; className?: string }) {
  const Icon = ZONE_ICONS[zone?.icon ?? "box"] ?? Box;
  const color = zone?.color ?? "#64748B";
  return (
    <span
      className={cn("grid shrink-0 place-items-center rounded-xl border", className)}
      style={{ width: size, height: size, color, background: `color-mix(in srgb, ${color} 14%, transparent)`, borderColor: `color-mix(in srgb, ${color} 35%, transparent)` }}
    >
      <Icon style={{ width: size * 0.5, height: size * 0.5 }} />
    </span>
  );
}
