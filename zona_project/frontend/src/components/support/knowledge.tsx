"use client";

import { useQuery } from "@tanstack/react-query";
import { BotMessageSquare, FlaskConical, Plus, Star } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";

import { supportApi, type EntryStatus, type TestResult } from "./api";
import { EntryBadge, fmtDate, stageLabel, useSupportMutation } from "./common";
import { EntryEditor } from "./entry-editor";
import { useSt } from "./i18n";

const STATUSES: (EntryStatus | "all")[] = ["approved", "review", "new", "archived", "rejected", "all"];

export function SupportKnowledge() {
  return <Suspense><KnowledgeInner /></Suspense>;
}

/** Bilim bazasi: shablonlar va savol-javoblar jadvali, tahrirlovchi va "sinab ko'rish". */
function KnowledgeInner() {
  const t = useSt();
  const params = useSearchParams();
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("approved");
  const [kind, setKind] = useState<"" | "faq" | "template">("");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<number | null>(() => Number(params.get("entry")) || null);
  const [open, setOpen] = useState(() => !!Number(params.get("entry")));
  const list = useQuery({
    queryKey: ["support", "entries", status, kind, q],
    queryFn: () => supportApi.entries({ status, ...(kind ? { kind } : {}), ...(q ? { q } : {}) }),
  });
  const edit = (id: number | null) => { setEditing(id); setOpen(true); };

  return (
    <Page>
      <PageHeader title={t("kbTitle")} description={t("kbDesc")}
        actions={<Button onClick={() => edit(null)}><Plus className="size-4" />{t("newEntry")}</Button>} />
      <TestBox />
      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Tabs value={status} onValueChange={(v) => setStatus(v as typeof status)}>
          <TabsList>{STATUSES.map((s) => <TabsTrigger key={s} value={s}>{s === "all" ? t("all") : t(`e_${s}`)}</TabsTrigger>)}</TabsList>
        </Tabs>
        <Tabs value={kind || "any"} onValueChange={(v) => setKind(v === "any" ? "" : (v as typeof kind))}>
          <TabsList>
            <TabsTrigger value="any">{t("all")}</TabsTrigger>
            <TabsTrigger value="template">{t("k_template")}</TabsTrigger>
            <TabsTrigger value="faq">{t("k_faq")}</TabsTrigger>
          </TabsList>
        </Tabs>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-9 max-w-64" />
      </div>
      {list.isLoading && <Skeleton className="h-64" />}
      {list.data && list.data.length === 0 && <EmptyState icon={BotMessageSquare} title={t("empty")} />}
      {list.data && list.data.length > 0 && (
        <Card className="p-0">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("title")}</TableHead>
                <TableHead>{t("kind")}</TableHead>
                <TableHead>{t("status")}</TableHead>
                <TableHead className="text-right">{t("uses")}</TableHead>
                <TableHead className="text-right">{t("rating")}</TableHead>
                <TableHead>{t("createdBy")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {list.data.map((e) => (
                <TableRow key={e.id} className="cursor-pointer" onClick={() => edit(e.id)}>
                  <TableCell className="max-w-md">
                    <div className="flex items-center gap-1.5 truncate font-medium">
                      {e.priority && <Star className="size-3.5 shrink-0 fill-warning text-warning" />}{e.title}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{e.answer}</div>
                    {e.pending && <Badge variant="outline" className="mt-1 border-warning/50 font-normal text-warning">{t("pendingEdit")}</Badge>}
                  </TableCell>
                  <TableCell className="text-xs">{t(`k_${e.kind}`)}</TableCell>
                  <TableCell><EntryBadge status={e.status} t={t} /></TableCell>
                  <TableCell className="text-right font-mono text-xs">{e.uses}</TableCell>
                  <TableCell className="text-right font-mono text-xs">👍 {e.likes} · 👎 {e.dislikes}</TableCell>
                  <TableCell className="text-xs text-muted-foreground">{e.author || "—"}<div>{fmtDate(e.updated_at, false)}</div></TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      )}
      <EntryEditor entryId={editing} open={open} onOpenChange={setOpen} />
    </Page>
  );
}

function TestBox() {
  const t = useSt();
  const [text, setText] = useState("");
  const [res, setRes] = useState<TestResult | null>(null);
  const run = useSupportMutation((v: string) => supportApi.test(v, true));
  return (
    <Card className="mb-4 gap-2 p-3">
      <div className="flex items-center gap-1.5 text-sm font-medium"><FlaskConical className="size-4" />{t("testTitle")}</div>
      <p className="text-xs text-muted-foreground">{t("testHint")}</p>
      <div className="flex flex-col gap-2 sm:flex-row">
        <Textarea rows={2} value={text} onChange={(e) => setText(e.target.value)} className="flex-1" />
        <Button variant="outline" className="sm:self-end" disabled={text.trim().length < 3 || run.isPending}
          onClick={() => run.mutate(text, { onSuccess: setRes })}>{t("testRun")}</Button>
      </div>
      {res && (
        <div className="rounded-lg border bg-muted/30 p-2 text-sm">
          {res.text && !res.needs_human ? (
            <>
              <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <Badge variant="outline" className="font-normal">{stageLabel(res.stage, t)}</Badge>
                <span>{res.confidence}% {t("confidence")}</span>
                {res.entry_title && <span>· {res.entry_title}</span>}
                {res.unapproved && <span className="text-warning">· {t("unapprovedWarn")}</span>}
              </div>
              <p className="whitespace-pre-wrap">{res.text}</p>
            </>
          ) : <p className="text-muted-foreground">{t("testNothing")}{res.note && ` — ${res.note}`}</p>}
          {res.responsible[0] && (
            <p className="mt-1 text-xs text-muted-foreground">
              {t("responsible")}: {res.responsible[0].name} {res.responsible[0].telegram.map((x) => "@" + x).join(" ")}
            </p>
          )}
        </div>
      )}
    </Card>
  );
}
