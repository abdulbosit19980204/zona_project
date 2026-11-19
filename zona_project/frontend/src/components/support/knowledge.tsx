"use client";

import { useQuery } from "@tanstack/react-query";
import { BotMessageSquare, FlaskConical, Images, ListChecks, Paperclip, Plus, Search, Star, ThumbsDown, ThumbsUp } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { cn } from "@/lib/utils";

import { supportApi, type EntryStatus, type TestResult } from "./api";
import { EntryBadge, fmtDate, stageLabel, useSupportMutation } from "./common";
import { EntryEditor } from "./entry-editor";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";

const STATUSES: (EntryStatus | "all")[] = ["approved", "review", "new", "archived", "rejected", "all"];
type KindFilter = "any" | "faq" | "template";
const KINDS: KindFilter[] = ["any", "template", "faq"];

export function SupportKnowledge() {
  return <Suspense><KnowledgeInner /></Suspense>;
}

function Pills<T extends string>({ value, options, onChange, label }: { value: T; options: T[]; onChange: (v: T) => void; label: (v: T) => string }) {
  return (
    <div className="flex flex-wrap gap-1">
      {options.map((o) => (
        <button key={o} type="button" onClick={() => onChange(o)}
          className={cn("rounded-full border px-2.5 py-1 text-xs transition-colors", value === o ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>
          {label(o)}
        </button>
      ))}
    </div>
  );
}

/** Bilim bazasi: kartochkalar, tezkor qidiruv va filtrlar; bosilsa — muharrir; «Sinab ko'rish» — alohida oynada. */
function KnowledgeInner() {
  const t = useSt();
  const params = useSearchParams();
  const [status, setStatus] = useState<(typeof STATUSES)[number]>("approved");
  const [kind, setKind] = useState<KindFilter>("any");
  const [q, setQ] = useState("");
  const [editing, setEditing] = useState<number | null>(() => Number(params.get("entry")) || null);
  const [open, setOpen] = useState(() => !!Number(params.get("entry")));
  const [testing, setTesting] = useState(false);
  const list = useQuery({
    queryKey: ["support", "entries", status, kind, q],
    queryFn: () => supportApi.entries({ status, ...(kind !== "any" ? { kind } : {}), ...(q ? { q } : {}) }),
  });
  const edit = (id: number | null) => { setEditing(id); setOpen(true); };

  return (
    <SupportShell title={t("kbTitle")} description={t("kbDesc")}
      actions={(
        <>
          <Button variant="outline" onClick={() => setTesting(true)}><FlaskConical className="size-4" />{t("testTitle")}</Button>
          <Button onClick={() => edit(null)}><Plus className="size-4" />{t("newEntry")}</Button>
        </>
      )}>
      <div className="mb-4 grid gap-3 rounded-xl border bg-card p-3 md:grid-cols-[minmax(220px,1fr)_auto]">
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kbSearch")} className="h-9 pl-8" />
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <Pills value={status} options={STATUSES} onChange={setStatus} label={(s) => (s === "all" ? t("all") : t(`e_${s}` as SKey))} />
          <Pills value={kind} options={KINDS} onChange={setKind} label={(k) => (k === "any" ? t("allKinds") : t(`k_${k}` as SKey))} />
        </div>
      </div>

      {list.isLoading && <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">{[0, 1, 2, 3, 4, 5].map((i) => <Skeleton key={i} className="h-36" />)}</div>}
      {list.data && list.data.length === 0 && (
        <EmptyState icon={BotMessageSquare} title={t("empty")} action={<Button onClick={() => edit(null)}><Plus className="size-4" />{t("newEntry")}</Button>} />
      )}
      {list.data && list.data.length > 0 && (
        <>
          <p className="mb-2 text-xs text-muted-foreground">{t("kbCount", { n: list.data.length })}</p>
          <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
            {list.data.map((e) => (
              <button key={e.id} type="button" onClick={() => edit(e.id)}
                className="group flex flex-col gap-2 rounded-xl border bg-card p-4 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md">
                <div className="flex items-start gap-2">
                  {e.priority && <Star className="mt-0.5 size-4 shrink-0 fill-warning text-warning" />}
                  <span className="line-clamp-2 flex-1 font-medium leading-snug">{e.title}</span>
                </div>
                <p className="line-clamp-3 text-sm text-muted-foreground">{e.answer}</p>
                <div className="mt-auto flex flex-wrap items-center gap-1.5 pt-1 text-xs">
                  <EntryBadge status={e.status} t={t} />
                  <Badge variant="outline" className="font-normal">{t(`k_${e.kind}` as SKey)}</Badge>
                  {e.pending && <Badge variant="outline" className="border-warning/50 font-normal text-warning">{t("pendingEdit")}</Badge>}
                  {(e.attachments?.length ?? 0) > 0 && <span className="inline-flex items-center gap-0.5 text-muted-foreground"><Paperclip className="size-3" />{e.attachments.length}</span>}
                  {(e.image_examples_count ?? 0) > 0 && <span className="inline-flex items-center gap-0.5 text-muted-foreground"><Images className="size-3" />{e.image_examples_count}</span>}
                  {e.ask_first && <span className="inline-flex items-center text-muted-foreground" title={t("askFirst")}><ListChecks className="size-3" /></span>}
                  <span className="ml-auto inline-flex items-center gap-2 text-muted-foreground">
                    <span title={t("uses")}>{e.uses}×</span>
                    <span className="inline-flex items-center gap-0.5"><ThumbsUp className="size-3" />{e.likes}</span>
                    <span className="inline-flex items-center gap-0.5"><ThumbsDown className="size-3" />{e.dislikes}</span>
                  </span>
                </div>
                <div className="text-[11px] text-muted-foreground">{e.author || "—"} · {fmtDate(e.updated_at, false)}</div>
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
