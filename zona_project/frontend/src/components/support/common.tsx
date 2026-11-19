"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { errorMessage } from "@/lib/api/client";
import { cn } from "@/lib/utils";

import type { EntryStatus, Mode, MsgStatus } from "./api";
import type { SKey, ST } from "./i18n";

export { fmtDate } from "@/components/qrdrive/common";

const MSG_TONE: Record<MsgStatus, string> = {
  new: "border-primary/50 text-primary",
  answered: "border-success/50 text-success",
  drafted: "border-violet-500/50 text-violet-500",
  escalated: "border-warning/50 text-warning",
  ignored: "text-muted-foreground",
  closed: "text-muted-foreground",
};
const ENTRY_TONE: Record<EntryStatus, string> = {
  new: "border-primary/50 text-primary",
  review: "border-warning/50 text-warning",
  approved: "border-success/50 text-success",
  rejected: "border-destructive/50 text-destructive",
  archived: "text-muted-foreground",
};
const MODE_TONE: Record<Mode | "inherit", string> = {
  off: "text-muted-foreground",
  shadow: "border-violet-500/50 text-violet-500",
  live: "border-success/50 text-success",
  inherit: "text-muted-foreground",
};

export function MsgBadge({ status, t }: { status: MsgStatus; t: ST }) {
  return <Badge variant="outline" className={cn("font-normal", MSG_TONE[status])}>{t(`m_${status}` as SKey)}</Badge>;
}

export function EntryBadge({ status, t }: { status: EntryStatus; t: ST }) {
  return <Badge variant="outline" className={cn("font-normal", ENTRY_TONE[status])}>{t(`e_${status}` as SKey)}</Badge>;
}

export function ModeBadge({ mode, t }: { mode: Mode | "inherit"; t: ST }) {
  return <Badge variant="outline" className={cn("font-normal", MODE_TONE[mode])}>{t(`mode_${mode}` as SKey)}</Badge>;
}

export function stageLabel(stage: string, t: ST) {
  return stage ? t(`s_${stage}` as SKey) : "";
}

/** Mutatsiya: muvaffaqiyatda support so'rovlarini yangilaydi va xabar ko'rsatadi. */
export function useSupportMutation<V, R>(fn: (v: V) => Promise<R>, success?: string | ((r: R) => string)) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: async (r) => {
      await qc.invalidateQueries({ queryKey: ["support"] });
      if (success) toast.success(typeof success === "function" ? success(r) : success);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
}

/** Ko'p qatorli matn <-> ro'yxat. */
export const lines = (s: string) => s.split("\n").map((x) => x.trim()).filter(Boolean);
export const unlines = (a: string[] | undefined) => (a ?? []).join("\n");
