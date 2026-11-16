"use client";

import { AnimatePresence, motion } from "framer-motion";
import { Box, Hexagon, PanelRightClose, PanelRightOpen, UserRound, UsersRound } from "lucide-react";
import dynamic from "next/dynamic";
import { useTheme } from "next-themes";
import { useTranslations } from "next-intl";
import { useState } from "react";

import { RoleLine } from "@/components/common/role";
import { ZoneIcon } from "@/components/common/zone-icon";
import { InfoPanel } from "@/components/panels/info-panels";
import type { ScenePalette } from "@/components/three/responsibility-scene";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useModel, useScope } from "@/hooks/use-org";
import { ROLE_ORDER } from "@/lib/model";
import { cn } from "@/lib/utils";
import { useUI } from "@/stores/ui";

// WebGL faqat brauzerda; alohida bo'lak bo'lib yuklanadi.
const ResponsibilityScene = dynamic(
  () => import("@/components/three/responsibility-scene").then((m) => m.ResponsibilityScene),
  { ssr: false, loading: () => <Skeleton className="size-full rounded-none" /> },
);

// three.js CSS o'zgaruvchilarini o'qiy olmaydi — mavzu uchun aniq ranglar.
const PALETTES: Record<"dark" | "light", ScenePalette> = {
  dark: {
    background: "#0B1020", grid: "#1E2A44", primary: "#3987FF", violet: "#8667FF", cyan: "#35C6E8",
    warning: "#F59E0B", danger: "#EF4444", muted: "#64748B", text: "#F1F5F9", platform: "#1C2742", head: "#E2E8F0",
  },
  light: {
    background: "#F6F8FC", grid: "#D9E0EC", primary: "#2563EB", violet: "#7C5CF0", cyan: "#0EA5C6",
    warning: "#D97706", danger: "#DC2626", muted: "#94A3B8", text: "#0F172A", platform: "#E3E9F3", head: "#F8E7D6",
  },
};

/** 3D mas'uliyat xaritasi: kim qaysi jarayonga qanday rol bilan bog'langan — fazoviy ko'rinishda. */
export function ResponsibilityMap() {
  const t = useTranslations();
  const model = useModel();
  const { scope } = useScope();
  const { resolvedTheme } = useTheme();
  const hiddenRoles = useUI((s) => s.hiddenRoles);
  const toggleRole = useUI((s) => s.toggleRole);
  const [selected, setSelected] = useState<string | null>(null);
  const [panel, setPanel] = useState(true);

  return (
    <div className="flex h-full">
      <div className="relative min-w-0 flex-1">
        <ResponsibilityScene
          model={model}
          palette={PALETTES[resolvedTheme === "light" ? "light" : "dark"]}
          selected={selected}
          onSelect={setSelected}
          hiddenRoles={hiddenRoles}
          scope={scope}
        />
        <div className="pointer-events-none absolute inset-x-5 top-4 z-10 flex items-start gap-3">
          <div className="pointer-events-auto">
            <h1 className="flex items-center gap-2 text-lg font-semibold tracking-tight"><Box className="size-4 text-primary" />{t("nav.responsibilityMap")}</h1>
            <p className="text-xs text-muted-foreground">{t("map3d.hint")}</p>
          </div>
          <div className="flex-1" />
          <Button className="pointer-events-auto" variant="outline" size="icon" onClick={() => setPanel((p) => !p)} aria-label={t("org.panel")}>
            {panel ? <PanelRightClose className="size-4" /> : <PanelRightOpen className="size-4" />}
          </Button>
        </div>
        <div className="glass absolute bottom-4 left-1/2 z-10 flex max-w-[calc(100%-2rem)] -translate-x-1/2 items-center gap-1 overflow-x-auto rounded-2xl border p-1.5 shadow-lg">
          {ROLE_ORDER.map((r) => (
            <button
              key={r}
              onClick={() => toggleRole(r)}
              className={cn("flex h-8 shrink-0 items-center gap-2 rounded-xl px-2.5 text-xs hover:bg-muted", hiddenRoles.includes(r) && "opacity-40")}
              title={t(`roles.hint.${r}`)}
            >
              <RoleLine role={r} />{t(`roles.${r}`)}
            </button>
          ))}
          <span className="mx-1 h-5 w-px bg-border" />
          <span className="flex shrink-0 items-center gap-1.5 px-2 text-xs text-muted-foreground"><UserRound className="size-3.5 text-cyan" />{t("map3d.member")}</span>
          <span className="flex shrink-0 items-center gap-1.5 px-2 text-xs text-muted-foreground"><UsersRound className="size-3.5 text-violet" />{t("map3d.team")}</span>
          <span className="flex shrink-0 items-center gap-1.5 px-2 text-xs text-muted-foreground"><Hexagon className="size-3.5" />{t("map3d.department")}</span>
          <span className="flex shrink-0 items-center gap-1.5 px-2 text-xs text-muted-foreground"><span className="size-2 rounded-full bg-warning" />{t("workload.excessive")}</span>
        </div>
        {/* zonalar: jarayon ikonkasi zonasiga qarab */}
        <div className="glass absolute left-4 top-20 z-10 hidden w-56 rounded-2xl border p-2 shadow-lg md:block">
          <div className="px-2 pb-1.5 pt-1 text-[10.5px] font-semibold uppercase tracking-wider text-muted-foreground">{t("map3d.zones")}</div>
          {model.state.zones.map((z) => (
            <button
              key={z.id} type="button" onClick={() => setSelected(`zone:${z.id}`)}
              className={cn("flex w-full items-center gap-2 rounded-lg px-2 py-1 text-left text-xs hover:bg-muted", selected === `zone:${z.id}` && "bg-muted")}
            >
              <ZoneIcon zone={z} size={22} className="rounded-md" />
              <span className="min-w-0 flex-1 truncate">{z.name}</span>
              <span className="font-mono text-[10.5px] text-muted-foreground">{model.state.processes.filter((p) => p.zone === z.id).length}</span>
            </button>
          ))}
        </div>
      </div>
      <AnimatePresence initial={false}>
        {panel && (
          <motion.aside
            key="panel"
            initial={{ width: 0, opacity: 0 }}
            animate={{ width: 384, opacity: 1 }}
            exit={{ width: 0, opacity: 0 }}
            transition={{ type: "spring", stiffness: 380, damping: 38 }}
            className="shrink-0 overflow-hidden border-l bg-card/60 backdrop-blur"
          >
            <div className="h-full w-96 overflow-y-auto">
              <InfoPanel selected={selected?.startsWith("zone:") ? null : selected} onSelect={setSelected} />
            </div>
          </motion.aside>
        )}
      </AnimatePresence>
    </div>
  );
}
