"use client";

import { ChevronLeft, ChevronRight, Download, ScrollText, Search } from "lucide-react";
import { useState } from "react";

import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useQr } from "@/hooks/use-qrdrive";
import { download, type AuditRow } from "@/lib/api/qrdrive";

import { QrGuard, fmtDate } from "./common";
import { useQt, type QKey } from "./i18n";

const PAGE = 100;

function detailText(d: Record<string, unknown>): string {
  return Object.entries(d ?? {}).map(([k, v]) => {
    if (v && typeof v === "object" && "old" in (v as object) && "new" in (v as object)) {
      const c = v as { old: unknown; new: unknown };
      return `${k}: ${JSON.stringify(c.old)} → ${JSON.stringify(c.new)}`;
    }
    return `${k}: ${typeof v === "string" ? v : JSON.stringify(v)}`;
  }).join("; ");
}

/** Jurnal: admin amallari (eski → yangi qiymat, maxfiylar yashirilgan), bot va API hodisalari. */
export function QrAudit() {
  const t = useQt();
  const [q, setQ] = useState("");
  const [kind, setKind] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [page, setPage] = useState(1);
  const filters = { q: q || undefined, actor_kind: kind === "all" ? undefined : kind, date_from: from || undefined, date_to: to || undefined };
  const query = useQr<{ items: AuditRow[]; total: number }>(["audit"], "audit", { ...filters, page, page_size: PAGE });
  const pages = Math.max(1, Math.ceil((query.data?.total ?? 0) / PAGE));

  return (
    <Page>
      <PageHeader title={t("auditTitle")} description={t("auditDesc")}
        actions={<Button variant="outline" onClick={() => download("audit/export.csv", "qrdrive-jurnal.csv", filters)}><Download className="size-4" />{t("export")}</Button>} />
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <div className="relative w-72">
          <Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder={t("search")} className="pl-8" />
        </div>
        <Select value={kind} onValueChange={(v) => { setKind(v); setPage(1); }}>
          <SelectTrigger className="w-40"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("colWho")}: {t("all")}</SelectItem>
            {(["admin", "bot", "api", "system"] as const).map((k) => <SelectItem key={k} value={k}>{t(`kind_${k}` as QKey)}</SelectItem>)}
          </SelectContent>
        </Select>
        <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="w-40" aria-label={t("dateFrom")} />
        <Input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="w-40" aria-label={t("dateTo")} />
      </div>
      <QrGuard query={query}>
        {!query.data?.items.length ? <EmptyState icon={ScrollText} title={t("emptyHint")} /> : (
          <Card className="gap-0 overflow-hidden p-0">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-40">{t("colDate")}</TableHead>
                  <TableHead className="w-44">{t("colWho")}</TableHead>
                  <TableHead className="w-48">{t("colAction")}</TableHead>
                  <TableHead>{t("colTarget")}</TableHead>
                  <TableHead>{t("colDetails")}</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {query.data.items.map((a) => (
                  <TableRow key={a.id}>
                    <TableCell className="text-xs text-muted-foreground">{fmtDate(a.at)}</TableCell>
                    <TableCell><div className="truncate text-sm">{a.actor || "—"}</div>
                      <Badge variant="outline" className="text-[10px]">{t(`kind_${a.actor_kind}` as QKey)}</Badge></TableCell>
                    <TableCell className="font-mono text-xs">{a.action}</TableCell>
                    <TableCell className="max-w-56 truncate text-sm">{a.target}</TableCell>
                    <TableCell className="max-w-96 truncate text-xs text-muted-foreground" title={detailText(a.details)}>{detailText(a.details)}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Card>
        )}
        {pages > 1 && (
          <div className="mt-3 flex items-center justify-end gap-2 text-sm">
            <span className="text-muted-foreground">{t("total", { n: query.data?.total ?? 0 })}</span>
            <Button size="icon" variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}><ChevronLeft className="size-4" /></Button>
            <span>{page} / {pages}</span>
            <Button size="icon" variant="outline" disabled={page >= pages} onClick={() => setPage(page + 1)}><ChevronRight className="size-4" /></Button>
          </div>
        )}
      </QrGuard>
    </Page>
  );
}
