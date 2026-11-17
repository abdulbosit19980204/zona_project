"use client";

import { QrCode } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { useQrAction, useQrNotifications } from "@/hooks/use-qrdrive";
import { qrApi } from "@/lib/api/qrdrive";
import { cn } from "@/lib/utils";

import { fmtDate } from "./common";
import { useQt } from "./i18n";

const LEVEL: Record<string, string> = { error: "bg-destructive", warning: "bg-warning", success: "bg-success", info: "bg-primary" };

/** QR Drive bildirishnomalari (qo'ng'iroqcha). Servis ishlamasa ko'rinmaydi. */
export function QrBell() {
  const t = useQt();
  const { data, isError } = useQrNotifications();
  const read = useQrAction(async () => qrApi.post("notifications/read", {}));
  if (isError || !data) return null;
  const count = data.unread;
  return (
    <Popover onOpenChange={(open) => !open && count > 0 && read.mutate()}>
      <PopoverTrigger asChild>
        <Button variant="outline" size="icon" className="relative" aria-label={t("notifications")}>
          <QrCode className="size-4" />
          {count > 0 && (
            <span className="absolute -right-1.5 -top-1.5 grid h-[18px] min-w-[18px] place-items-center rounded-full bg-warning px-1 font-mono text-[10px] text-white ring-2 ring-background">
              {Math.min(99, count)}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-96 p-0">
        <div className="flex items-center border-b px-4 py-3 text-sm font-semibold">{t("notifications")}</div>
        <div className="max-h-[60vh] overflow-y-auto p-2">
          {!data.items.length && <div className="px-3 py-6 text-center text-sm text-muted-foreground">{t("noNotifications")}</div>}
          {data.items.map((n) => (
            <Link key={n.id} href={n.link || "/qr"} className={cn("flex gap-3 rounded-lg px-3 py-2.5 hover:bg-muted", !n.read && "bg-primary/5")}>
              <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", LEVEL[n.level] ?? LEVEL.info)} />
              <span className="min-w-0">
                <span className="block text-sm font-medium">{n.title}</span>
                {n.body && <span className="block text-xs text-muted-foreground">{n.body}</span>}
                <span className="block text-[11px] text-muted-foreground/80">{fmtDate(n.at)}</span>
              </span>
            </Link>
          ))}
        </div>
      </PopoverContent>
    </Popover>
  );
}
