"use client";

import { CheckCircle2, Lightbulb, RefreshCw, TriangleAlert } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { useState } from "react";

import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { useQr, useQrAction } from "@/hooks/use-qrdrive";
import { qrApi, type HumanError, type QrFile } from "@/lib/api/qrdrive";

import { QrGuard, StatusBadge, fmtDate } from "./common";
import { FileSheet } from "./file-sheet";
import { errorText, useQt } from "./i18n";

interface Group extends HumanError { count: number; items: QrFile[] }

/** Xatolar markazi: xato turlari bo'yicha guruhlangan, oddiy tilda sabab va tavsiya, qayta urinish. */
export function QrErrors() {
  const t = useQt();
  const params = useSearchParams();
  const [openId, setOpenId] = useState<number | null>(params.get("file") ? Number(params.get("file")) : null);
  const q = useQr<{ groups: Group[]; total: number }>(["errors"], "errors", undefined, { refetchInterval: 20_000 });
  const retry = useQrAction(async (body: { ids?: number[]; kind?: string }) =>
    (await qrApi.post<{ retried: number }>("errors/retry", body)).data, (r) => t("retried", { n: r.retried }));
  const failedTotal = q.data?.groups.reduce((n, g) => n + g.items.filter((i) => i.status === "failed").length, 0) ?? 0;

  return (
    <Page>
      <PageHeader title={t("errTitle")} description={t("errDesc")}
        actions={failedTotal > 0 && <Button onClick={() => retry.mutate({})} disabled={retry.isPending}><RefreshCw className="size-4" />{t("retryAll")}</Button>} />
      <QrGuard query={q}>
        {!q.data?.groups.length ? <EmptyState icon={CheckCircle2} title={t("errEmpty")} hint={t("errEmptyHint")} /> : (
          <div className="grid gap-4">
            {q.data.groups.map((g) => {
              const text = errorText(t, g)!;
              return (
                <Card key={g.kind} className="gap-0 overflow-hidden p-0">
                  <div className="flex flex-wrap items-start gap-3 border-b bg-destructive/5 px-5 py-4">
                    <TriangleAlert className="mt-0.5 size-5 shrink-0 text-destructive" />
                    <div className="min-w-0 flex-1">
                      <div className="font-medium">{text.title} <span className="font-mono text-sm text-muted-foreground">· {g.count}</span></div>
                      <div className="mt-1 flex items-start gap-1.5 text-sm text-muted-foreground"><Lightbulb className="mt-0.5 size-3.5 shrink-0 text-warning" />
                        <span><b className="font-medium text-foreground">{t("whatToDo")}:</b> {text.hint}</span></div>
                    </div>
                    <Button size="sm" variant="outline" onClick={() => retry.mutate({ kind: g.kind })}><RefreshCw className="size-4" />{t("retryAll")}</Button>
                  </div>
                  <div className="divide-y">
                    {g.items.map((f) => (
                      <div key={f.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                        <button className="min-w-0 flex-1 truncate text-left hover:text-primary" onClick={() => setOpenId(f.id)}>
                          {f.original_name}<span className="text-muted-foreground"> · {f.employee_name || "—"}</span>
                        </button>
                        <span className="hidden text-xs text-muted-foreground sm:block">{fmtDate(f.created_at)}</span>
                        <StatusBadge status={f.status} />
                        {f.status === "failed" && (
                          <Button size="sm" variant="ghost" onClick={() => retry.mutate({ ids: [f.id] })}><RefreshCw className="size-4" />{t("retryOne")}</Button>
                        )}
                      </div>
                    ))}
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </QrGuard>
      <FileSheet fileId={openId} onClose={() => setOpenId(null)} />
    </Page>
  );
}
