"use client";

import { useMutation } from "@tanstack/react-query";
import { FileSpreadsheet, Loader2, Printer, Sparkles } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { toast } from "sonner";

import { Markdown } from "@/components/common/markdown";
import { STATUS_COLOR } from "@/components/common/time";
import { Page, PageHeader } from "@/components/common/page";
import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useModel } from "@/hooks/use-org";
import { errorMessage } from "@/lib/api/client";
import { aiApi, orgApi } from "@/lib/api/endpoints";
import { fmtHours } from "@/lib/model";

/** Hisobotlar: Excel eksport, AI audit va chop etiladigan qisqa hisobot. */
export function Reports() {
  const t = useTranslations();
  const locale = useLocale();
  const model = useModel();
  const exporter = useMutation({
    mutationFn: orgApi.exportXlsx,
    onSuccess: (blob) => {
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `responsibility-${new Date().toISOString().slice(0, 10)}.xlsx`;
      a.click();
      URL.revokeObjectURL(url);
    },
    onError: (e) => toast.error(errorMessage(e)),
  });
  const audit = useMutation({ mutationFn: () => aiApi.audit(locale) });
  const pct = (v: number) => `${Math.round(v * 100)}%`;

  return (
    <Page>
      <PageHeader title={t("nav.reports")} description={t("reports.description")} />
      <div className="grid gap-4 md:grid-cols-3 print:hidden">
        <Card className="gap-3 p-5">
          <FileSpreadsheet className="size-6 text-success" />
          <div><div className="font-semibold">{t("reports.excel")}</div><p className="text-sm text-muted-foreground">{t("reports.excelHint")}</p></div>
          <Button variant="outline" className="mt-auto" disabled={exporter.isPending} onClick={() => exporter.mutate()}>
            {exporter.isPending && <Loader2 className="size-4 animate-spin" />}{t("reports.download")}
          </Button>
        </Card>
        <Card className="gap-3 p-5">
          <Sparkles className="size-6 text-primary" />
          <div><div className="font-semibold">{t("reports.aiAudit")}</div><p className="text-sm text-muted-foreground">{t("reports.aiAuditHint")}</p></div>
          <Button className="mt-auto" disabled={!model.state.meta.ai.audit || audit.isPending} onClick={() => audit.mutate()}>
            {audit.isPending && <Loader2 className="size-4 animate-spin" />}{model.state.meta.ai.audit ? t("reports.runAudit") : t("ask.aiOff")}
          </Button>
        </Card>
        <Card className="gap-3 p-5">
          <Printer className="size-6 text-violet" />
          <div><div className="font-semibold">{t("reports.print")}</div><p className="text-sm text-muted-foreground">{t("reports.printHint")}</p></div>
          <Button variant="outline" className="mt-auto" onClick={() => window.print()}>{t("reports.print")}</Button>
        </Card>
      </div>
      {audit.isError && <Alert variant="destructive" className="mt-4"><AlertDescription>{errorMessage(audit.error)}</AlertDescription></Alert>}
      {audit.data && (
        <Card className="mt-4 gap-2 p-5">
          <div className="text-xs text-muted-foreground">{audit.data.meta.model} · {audit.data.meta.latency_ms} ms</div>
          <Markdown text={audit.data.text} />
        </Card>
      )}
      <Card className="mt-4 gap-0 overflow-hidden p-0">
        <div className="border-b px-5 py-3">
          <div className="font-semibold">{t("reports.summary", { company: model.state.meta.company })}</div>
          <div className="text-xs text-muted-foreground">
            {t("reports.summaryHint", { owner: pct(model.coverage.owner), backup: pct(model.coverage.backup), issues: model.issueProcesses.length })}
          </div>
        </div>
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("nav.employees")}</TableHead>
              <TableHead>{t("org.department")}</TableHead>
              <TableHead className="text-right">{t("workload.tasks")}</TableHead>
              <TableHead className="text-right">{t("workload.owned")}</TableHead>
              <TableHead className="text-right">{t("workload.approvals")}</TableHead>
              <TableHead className="text-right">{t("panel.authority")}</TableHead>
              <TableHead className="text-right">{t("workload.score")}</TableHead>
              <TableHead className="text-right">{t("time.hPerWeek")}</TableHead>
              <TableHead className="text-right">{t("time.capacity")}</TableHead>
              <TableHead className="text-right">{t("time.utilShort")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {model.workload.map((w) => (
              <TableRow key={w.member.id}>
                <TableCell className="font-medium">{w.member.name}<div className="text-xs font-normal text-muted-foreground">{w.member.role}</div></TableCell>
                <TableCell className="text-muted-foreground">{model.dept.get(model.deptOf(w.member))?.name ?? "—"}</TableCell>
                <TableCell className="text-right font-mono">{w.tasks}</TableCell>
                <TableCell className="text-right font-mono">{w.owned}</TableCell>
                <TableCell className="text-right font-mono">{w.approvals}</TableCell>
                <TableCell className="text-right font-mono">{(model.authorities.get(w.member.id) ?? []).length}</TableCell>
                <TableCell className="text-right font-mono">{w.score}</TableCell>
                <TableCell className="text-right font-mono">{fmtHours(w.hours)}</TableCell>
                <TableCell className="text-right font-mono">{w.member.capacity}</TableCell>
                <TableCell className="text-right font-mono font-semibold" style={{ color: STATUS_COLOR[w.status] }}>{Math.round(w.util * 100)}%</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </Page>
  );
}
