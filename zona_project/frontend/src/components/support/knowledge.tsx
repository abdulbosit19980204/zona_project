"use client";

import { useQuery } from "@tanstack/react-query";
import { BotMessageSquare, FlaskConical, Images, ListChecks, ListTodo, Paperclip, Plus, Search, Star, ThumbsDown, ThumbsUp } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";

import { supportApi, type EntryStatus, type TestResult } from "./api";
import { EntryBadge, fmtDate, Segmented, stageLabel, useSupportMutation } from "./common";
import { EntryEditor } from "./entry-editor";
import { smartFilter } from "./smart-search";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";

const STATUSES: (EntryStatus | "all")[] = ["approved", "review", "new", "archived", "rejected", "all"];
type KindFilter = "any" | "faq" | "template";
const KINDS: KindFilter[] = ["any", "template", "faq"];

export function SupportKnowledge() {
  return <Suspense><KnowledgeInner /></Suspense>;
}

/** Bilim bazasi: qidiruv va filtrlar paneli, kartochkalar; bosilsa — muharrir; «Sinab ko'rish» — alohida oynada. */
function KnowledgeInner() {
  const t = useSt();
  const params = useSearchParams();
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("approved");
  const [kind, setKind] = useState<KindFilter>("any");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<number | null>(() => Number(params.get("entry")) || null);
  const [open, setOpen] = useState(() => !!Number(params.get("entry")));
  const [testing, setTesting] = useState(false);
  const stats = useQuery({ queryKey: ["support", "stats"], queryFn: () => supportApi.stats(7) });
  const counts = stats.data?.entries ?? {};
  const list = useQuery({
    queryKey: ["support", "entries", status, kind],
    queryFn: () => supportApi.entries({ status, ...(kind !== "any" ? { kind } : {}) }),
  });
  // smart qidiruv: kirill/lotin, apostrof va imlo xatosiga chidamli; eng mos yozuv birinchi
  const [onlyTask, setOnlyTask] = useState(false);
  const shown = useMemo(() => (list.data ? smartFilter(list.data.filter((e) => !onlyTask || e.creates_task), q,
    (e) => `${e.title} ${(e.questions ?? []).join(" ")} ${e.answer}`) : undefined), [list.data, q, onlyTask]);
  const edit = (id: number | null) => { setEditing(id); setOpen(true); };

  return (
    <SupportShell title={t("kbTitle")} description={t("kbDesc")}
      actions={(
        <>
          <Button size="sm" variant="outline" onClick={() => setTesting(true)}><FlaskConical className="size-4" />{t("testTitle")}</Button>
          <Button size="sm" onClick={() => edit(null)}><Plus className="size-4" />{t("newEntry")}</Button>
        </>
      )}>
      <div className="sticky top-0 z-10 -mx-1 mb-4 grid gap-2.5 rounded-xl border bg-card/95 p-3 shadow-xs backdrop-blur">
        <div className="flex flex-col gap-2.5 lg:flex-row lg:items-center">
          <div className="relative flex-1">
            <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kbSearch")} className="h-9 bg-muted/40 pl-8" />
          </div>
          <Segmented size="sm" value={kind} onChange={setKind} options={KINDS.map((k) => ({ value: k, label: k === "any" ? t("allKinds") : t(`k_${k}` as SKey) }))} />
          <button type="button" onClick={() => setOnlyTask(!onlyTask)}
            className={`inline-flex h-8 shrink-0 items-center gap-1.5 rounded-lg border px-3 text-xs font-medium transition-colors ${onlyTask ? "border-primary bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}>
            <ListTodo className="size-3.5" />{t("kbOnlyTask")}
          </button>
        </div>
        <Segmented size="sm" value={status} onChange={setStatus} className="w-full sm:w-auto"
          options={STATUSES.map((x) => ({ value: x, label: x === "all" ? t("all") : t(`e_${x}` as SKey), count: x === "all" ? undefined : counts[x] }))} />
      </div>

      {list.isLoading && <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-40" />)}</div>}
      {shown && shown.length === 0 && (
        <EmptyState icon={BotMessageSquare} title={t("empty")} action={<Button onClick={() => edit(null)}><Plus className="size-4" />{t("newEntry")}</Button>} />
      )}
      {shown && shown.length > 0 && (
        <>
          <p className="mb-2 text-xs text-muted-foreground">{t("kbCount", { n: shown.length })}</p>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
            {shown.map((e) => (
              <button key={e.id} type="button" onClick={() => edit(e.id)}
                className="group flex flex-col rounded-xl border bg-card text-left shadow-xs transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
                <div className="flex flex-1 flex-col gap-2 p-4">
                  <div className="flex items-center gap-1.5 text-xs">
                    <EntryBadge status={e.status} t={t} />
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{t(`k_${e.kind}` as SKey)}</span>
                    {e.pending && <span className="rounded bg-warning/10 px-1.5 py-0.5 text-[11px] text-warning">{t("pendingEdit")}</span>}
                    {e.creates_task && <span className="inline-flex items-center gap-0.5 rounded bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary"><ListTodo className="size-3" />{t("kbTask")}</span>}
                    {e.priority && <Star className="ml-auto size-4 fill-warning text-warning" />}
                  </div>
                  <span className="line-clamp-2 font-medium leading-snug group-hover:text-primary">{e.title}</span>
                  <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">{e.answer}</p>
                </div>
                <div className="flex items-center gap-3 border-t px-4 py-2 text-xs text-muted-foreground">
                  {(e.attachments?.length ?? 0) > 0 && <span className="inline-flex items-center gap-0.5" title={t("attachments")}><Paperclip className="size-3" />{e.attachments.length}</span>}
                  {(e.image_examples_count ?? 0) > 0 && <span className="inline-flex items-center gap-0.5"><Images className="size-3" />{e.image_examples_count}</span>}
                  {e.ask_first && <span className="inline-flex items-center" title={t("askFirst")}><ListChecks className="size-3" /></span>}
                  <span className="truncate">{e.author || "—"} · {fmtDate(e.updated_at, false)}</span>
                  <span className="ml-auto inline-flex shrink-0 items-center gap-2 tabular-nums">
                    <span title={t("uses")}>{e.uses}×</span>
                    <span className="inline-flex items-center gap-0.5"><ThumbsUp className="size-3" />{e.likes}</span>
                    <span className="inline-flex items-center gap-0.5"><ThumbsDown className="size-3" />{e.dislikes}</span>
                  </span>
                </div>
              </button>
            ))}
          </div>
        </>
      )}
      <EntryEditor entryId={editing} open={open} onOpenChange={setOpen} />
      <Dialog open={testing} onOpenChange={setTesting}>
        <DialogContent className="max-w-2xl">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><FlaskConical className="size-4" />{t("testTitle")}</DialogTitle></DialogHeader>
          <TestBox t={t} />
        </DialogContent>
      </Dialog>
    </SupportShell>
  );
}

function TestBox({ t }: { t: ST }) {
  const [text, setText] = useState("");
  const [res, setRes] = useState<TestResult | null>(null);
  const run = useSupportMutation((v: string) => supportApi.test(v, true));
  return (
    <div className="grid gap-3">
      <p className="text-sm text-muted-foreground">{t("testHint")}</p>
      <Textarea rows={3} value={text} onChange={(e) => setText(e.target.value)} placeholder={t("testPlaceholder")} />
      <Button className="justify-self-start" disabled={text.trim().length < 3 || run.isPending} onClick={() => run.mutate(text, { onSuccess: setRes })}>
        <FlaskConical className="size-4" />{t("testRun")}
      </Button>
      {res && (
        <Card className="gap-2 p-3 text-sm">
          {res.text && !res.needs_human ? (
            <>
              <div className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <Badge className="font-normal">{stageLabel(res.stage, t)}</Badge>
                <span>{res.confidence}% {t("confidence")}</span>
                {res.entry_title && <span>· {res.entry_title}</span>}
                {res.unapproved && <span className="text-warning">· {t("unapprovedWarn")}</span>}
              </div>
              <p className="whitespace-pre-wrap">{res.text}</p>
            </>
          ) : <p className="text-muted-foreground">{t("testNothing")}{res.note && ` — ${res.note}`}</p>}
          {res.responsible[0] && (
            <p className="text-xs text-muted-foreground">{t("responsible")}: {res.responsible[0].name} {res.responsible[0].telegram.map((x) => "@" + x).join(" ")}</p>
          )}
        </Card>
      )}
    </div>
  );
}
