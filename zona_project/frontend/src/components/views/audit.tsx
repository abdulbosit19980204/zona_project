"use client";

import { format } from "date-fns";
import { History, Search } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useState } from "react";

import { DATE_LOCALES, eventDetail } from "@/components/common/activity";
import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useEvents } from "@/hooks/use-org";
import type { EventKind } from "@/lib/api/types";

const KINDS: EventKind[] = ["created", "moved", "edited", "deleted", "member", "role", "approval"];

/** O'zgarishlar tarixi: kim, qachon, nimani o'zgartirdi. WebSocket orqali jonli yangilanadi. */
export function Audit() {
  const t = useTranslations();
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const { data, isLoading } = useEvents(500);
  const [kind, setKind] = useState<EventKind | "all">("all");
  const [query, setQuery] = useState("");
  const q = query.trim().toLowerCase();
  const list = (data ?? []).filter((e) =>
    (kind === "all" || e.kind === kind) &&
    (!q || `${e.subject} ${e.from_name} ${e.to_name} ${e.text} ${e.actor}`.toLowerCase().includes(q)));

  return (
    <Page>
      <PageHeader title={t("nav.audit")} description={t("audit.description")} />
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <div className="relative w-72"><Search className="absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
          <Input value={query} onChange={(e) => setQuery(e.target.value)} placeholder={t("audit.filter")} className="pl-8" /></div>
        <Select value={kind} onValueChange={(v) => setKind(v as EventKind | "all")}>
          <SelectTrigger className="w-48"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value="all">{t("audit.allKinds")}</SelectItem>
            {KINDS.map((k) => <SelectItem key={k} value={k}>{t(`events.${k}`)}</SelectItem>)}
          </SelectContent>
        </Select>
        <span className="text-sm text-muted-foreground">{t("audit.count", { count: list.length })}</span>
      </div>
      {isLoading && <Skeleton className="h-96 rounded-xl" />}
      {data && !list.length && <EmptyState icon={History} title={t("common.nothingFound")} />}
      {!!list.length && (
        <Card className="gap-0 overflow-hidden p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-44">{t("audit.when")}</TableHead>
                <TableHead className="w-32">{t("audit.kind")}</TableHead>
                <TableHead>{t("audit.subject")}</TableHead>
                <TableHead>{t("audit.detail")}</TableHead>
                <TableHead className="w-40">{t("audit.actor")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.map((e) => (
                <TableRow key={e.id}>
                  <TableCell className="font-mono text-xs text-muted-foreground">{format(new Date(e.at), "dd.MM.yyyy HH:mm", { locale: DATE_LOCALES[locale] })}</TableCell>
                  <TableCell><Badge variant="outline" className={e.kind === "deleted" ? "text-destructive" : undefined}>{t(`events.${e.kind}`)}</Badge></TableCell>
                  <TableCell className="max-w-sm whitespace-normal font-medium">{e.subject || e.to_name || e.from_name}</TableCell>
                  <TableCell className="max-w-md whitespace-normal text-muted-foreground">{eventDetail(e)}</TableCell>
                  <TableCell className="text-muted-foreground">{e.actor || "—"}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
    </Page>
  );
}
