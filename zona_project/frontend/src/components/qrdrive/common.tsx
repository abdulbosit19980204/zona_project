"use client";

import { format } from "date-fns";
import { Check, CircleHelp, Copy, RefreshCw, ServerOff } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Label } from "@/components/ui/label";
import { Skeleton } from "@/components/ui/skeleton";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { blobUrl, isQrDown, qrError, type FileStatus } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { useQt, type QKey } from "./i18n";

export function fmtDate(iso: string | null | undefined, withTime = true): string {
  if (!iso) return "—";
  return format(new Date(iso), withTime ? "dd.MM.yyyy HH:mm" : "dd.MM.yyyy");
}

export function useDuration() {
  const t = useQt();
  return (ms: number | null | undefined) => {
    if (ms === null || ms === undefined) return "—";
    if (ms < 60_000) return t("seconds", { n: (ms / 1000).toFixed(ms < 10_000 ? 1 : 0) });
    if (ms < 3_600_000) return t("minutes", { n: Math.round(ms / 60_000) });
    return t("hours", { n: (ms / 3_600_000).toFixed(1) });
  };
}

const STATUS_TONE: Record<FileStatus, string> = {
  delivered: "bg-success/15 text-success",
  failed: "bg-destructive/15 text-destructive",
  retrying: "bg-warning/15 text-warning",
  processing: "bg-primary/15 text-primary",
  queued: "bg-muted text-muted-foreground",
  awaiting: "bg-violet/15 text-violet",
  merged: "bg-muted text-muted-foreground",
};

export function StatusBadge({ status }: { status: FileStatus }) {
  const t = useQt();
  return <Badge className={cn("border-0 font-medium", STATUS_TONE[status])}>{t(`st_${status}` as QKey)}</Badge>;
}

export function Dot({ ok, unknown }: { ok: boolean; unknown?: boolean }) {
  return (
    <span className={cn("inline-block size-2 shrink-0 rounded-full",
      unknown ? "bg-muted-foreground/50" : ok ? "bg-success shadow-[0_0_8px_var(--success)]" : "bg-destructive")} />
  );
}

export function Help({ text }: { text?: string }) {
  if (!text) return null;
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="inline-grid size-4 place-items-center text-muted-foreground hover:text-foreground" aria-label="?">
          <CircleHelp className="size-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs text-xs leading-relaxed">{text}</TooltipContent>
    </Tooltip>
  );
}

export function FormRow({ label, help, hint, children, className }: { label: string; help?: string; hint?: string; children: ReactNode; className?: string }) {
  return (
    <div className={cn("grid gap-1.5", className)}>
      <Label className="flex items-center gap-1.5 text-[13px]">{label}<Help text={help} /></Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

export function CopyButton({ text, label, size = "sm" }: { text: string; label?: string; size?: "sm" | "icon" }) {
  const t = useQt();
  const [done, setDone] = useState(false);
  const copy = async () => {
    await navigator.clipboard.writeText(text);
    setDone(true);
    toast.success(t("copied"));
    setTimeout(() => setDone(false), 1500);
  };
  return (
    <Button type="button" variant="outline" size={size} onClick={copy} aria-label={t("copy")}>
      {done ? <Check className="size-4" /> : <Copy className="size-4" />}{size !== "icon" && (label ?? t("copy"))}
    </Button>
  );
}

/** Servis ishlamasa yoki xato bo'lsa — tushunarli panel; bo'lmasa sahifa mazmuni. */
export function QrGuard({ query, children, skeleton }: {
  query: { isPending: boolean; isError: boolean; error: unknown; refetch: () => unknown };
  children: ReactNode;
  skeleton?: ReactNode;
}) {
  const t = useQt();
  if (query.isPending) return <>{skeleton ?? <Skeleton className="h-80 rounded-xl" />}</>;
  if (query.isError) {
    const down = isQrDown(query.error);
    return (
      <div className="grid place-items-center rounded-xl border border-dashed px-6 py-16 text-center">
        <ServerOff className="mb-3 size-8 text-warning" />
        <div className="font-medium">{down ? t("serviceDown") : qrError(query.error)}</div>
        {down && <p className="mt-1 max-w-md text-sm text-muted-foreground">{t("serviceDownHint")}</p>}
        <Button variant="outline" className="mt-4" onClick={() => query.refetch()}><RefreshCw className="size-4" />{t("retry")}</Button>
      </div>
    );
  }
  return <>{children}</>;
}

export function ConfirmDialog({ open, onOpenChange, title, description, confirmLabel, destructive, onConfirm, pending }: {
  open: boolean; onOpenChange: (v: boolean) => void; title: string; description?: string; confirmLabel?: string;
  destructive?: boolean; onConfirm: () => void; pending?: boolean;
}) {
  const t = useQt();
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          {description && <DialogDescription>{description}</DialogDescription>}
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>{t("cancel")}</Button>
          <Button variant={destructive ? "destructive" : "default"} disabled={pending} onClick={onConfirm}>{confirmLabel ?? t("confirm")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** Avtorizatsiya talab qiladigan rasm/fayl (QR, preview) — blob URL orqali. */
export function useAuthBlob(path: string | null, params?: Record<string, unknown>) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState(false);
  const key = path ? path + JSON.stringify(params ?? {}) : "";
  useEffect(() => {
    if (!path) return;
    let alive = true;
    let current: string | null = null;
    blobUrl(path, params)
      .then((u) => {
        current = u;
        if (alive) {
          setUrl(u);
          setError(false);
        } else URL.revokeObjectURL(u);
      })
      .catch(() => alive && setError(true));
    return () => {
      alive = false;
      if (current) URL.revokeObjectURL(current);
      setUrl(null);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return { url, error };
}

export function AuthImage({ path, params, alt, className }: { path: string; params?: Record<string, unknown>; alt: string; className?: string }) {
  const { url } = useAuthBlob(path, params);
  if (!url) return <Skeleton className={cn("aspect-square", className)} />;
  // eslint-disable-next-line @next/next/no-img-element
  return <img src={url} alt={alt} className={className} />;
}
