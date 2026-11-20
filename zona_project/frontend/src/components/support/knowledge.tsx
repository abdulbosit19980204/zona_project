"use client";

import { useQuery } from "@tanstack/react-query";
import { BotMessageSquare, Check, CheckSquare, FlaskConical, Images, ListChecks, ListTodo, Paperclip, Plus, Route, Search, Shuffle, Star, ThumbsDown, ThumbsUp, X } from "lucide-react";
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
import { EntryBadge, fmtDate, SearchPicker, Segmented, stageLabel, useSupportMutation } from "./common";
import { EntryEditor } from "./entry-editor";
import { smartFilter } from "./smart-search";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";

const STATUSES: (EntryStatus | "all")[] = ["approved", "review", "new", "archived", "rejected", "all"];
type KindFilter = "any" | "faq" | "template";
const KINDS: KindFilter[] = ["any", "template", "faq"];

type Flag = "routing" | "images" | "variants" | "novariants" | "task";
type Sort = "used" | "images" | "new";

/** Faqat "falonchi hal qiladi" deb yo'naltiradigan (haqiqiy yechimi yo'q) javoblar — birinchi navbatda to'ldirish kerak. */
const isRouting = (a: string) => /hal qiladi|Avval \*\*.+\*\*ga yozing|Mas'ul: \*\*/i.test(a) && a.length < 320;
const uniq = <T extends { id: number | string; title: string }>(xs: T[]) => [...new Map(xs.map((x) => [String(x.id), x])).values()]
  .sort((a, b) => a.title.localeCompare(b.title));

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
  // filtrlar: mas'ul, zona, tezkor belgilar va tartib; qidiruv — smart (kirill/lotin, imlo xatosiga chidamli)
  const [resp, setResp] = useState("");
  const [zone, setZone] = useState("");
  const [flags, setFlags] = useState<Set<Flag>>(new Set());
  const [sort, setSort] = useState<Sort>("used");
  const toggleFlag = (f: Flag) => setFlags((s) => { const n = new Set(s); if (n.has(f)) n.delete(f); else n.add(f); return n; });
  const respOptions = useMemo(() => uniq((list.data ?? []).filter((e) => e.responsible).map((e) => ({ id: e.responsible!, title: e.responsible_name }))), [list.data]);
  const zoneOptions = useMemo(() => uniq((list.data ?? []).filter((e) => e.zone_name).map((e) => ({ id: e.zone_name, title: e.zone_name }))), [list.data]);
  const shown = useMemo(() => {
    if (!list.data) return undefined;
    const rows = list.data.filter((e) => (!resp || String(e.responsible) === resp) && (!zone || e.zone_name === zone)
      && (!flags.has("task") || e.creates_task) && (!flags.has("routing") || isRouting(e.answer))
      && (!flags.has("images") || (e.image_examples_count ?? 0) > 0) && (!flags.has("variants") || (e.variants?.length ?? 0) > 0)
      && (!flags.has("novariants") || !(e.variants?.length)));
    if (q.trim()) return smartFilter(rows, q, (e) => `${e.title} ${(e.questions ?? []).join(" ")} ${e.answer}`);
    const key = sort === "used" ? (e: (typeof rows)[number]) => -(e.uses ?? 0) : sort === "images"
      ? (e: (typeof rows)[number]) => -(e.image_examples_count ?? 0) : (e: (typeof rows)[number]) => -new Date(e.updated_at).getTime();
    return [...rows].sort((a, b) => key(a) - key(b));
  }, [list.data, q, resp, zone, flags, sort]);
  const [selecting, setSelecting] = useState(false);
  const [sel, setSel] = useState<Set<number>>(new Set());
  const bulk = useSupportMutation((a: "kind_template" | "kind_faq" | "mode_auto" | "mode_on" | "mode_off") => supportApi.bulk([...sel], a),
    (r) => t("bulkDone", { n: r.done }));
  const toggleSel = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const routingCount = useMemo(() => (list.data ?? []).filter((e) => isRouting(e.answer)).length, [list.data]);
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
          <Button size="sm" variant={selecting ? "default" : "outline"} className="h-8"
            onClick={() => { setSelecting(!selecting); setSel(new Set()); }}><CheckSquare className="size-4" />{t("kbSelect")}</Button>
        </div>
        {selecting && (
          <div className="flex flex-wrap items-center gap-2 rounded-lg border border-primary/30 bg-primary/5 p-2">
            <span className="text-xs font-medium">{t("selected", { n: sel.size })}</span>
            <Button size="sm" variant="ghost" className="h-7 text-xs" onClick={() => setSel(new Set((shown ?? []).map((e) => e.id)))}>{t("kbSelectAll")}</Button>
            <span className="mx-1 h-4 w-px bg-border" />
            <Button size="sm" className="h-7 text-xs" disabled={!sel.size || bulk.isPending} onClick={() => bulk.mutate("kind_template")}>{t("kbToTemplate")}</Button>
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!sel.size || bulk.isPending} onClick={() => bulk.mutate("kind_faq")}>{t("kbToFaq")}</Button>
            <span className="mx-1 h-4 w-px bg-border" />
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!sel.size || bulk.isPending} onClick={() => bulk.mutate("mode_on")}>{t("mode_on")}</Button>
            <Button size="sm" variant="outline" className="h-7 text-xs" disabled={!sel.size || bulk.isPending} onClick={() => bulk.mutate("mode_off")}>{t("mode_offL")}</Button>
            <Button size="sm" variant="ghost" className="h-7 text-xs" disabled={!sel.size || bulk.isPending} onClick={() => bulk.mutate("mode_auto")}>{t("mode_auto")}</Button>
          </div>
        )}
        <div className="flex flex-wrap items-center gap-2">
          <Segmented size="sm" value={status} onChange={setStatus}
            options={STATUSES.map((x) => ({ value: x, label: x === "all" ? t("all") : t(`e_${x}` as SKey), count: x === "all" ? undefined : counts[x] }))} />
          <SearchPicker value={resp} onChange={setResp} className="h-8 w-48 text-xs" options={respOptions}
            placeholder={t("kbResp")} searchPlaceholder={t("search")} emptyText={t("pickNone")} />
          {zoneOptions.length > 0 && (
            <SearchPicker value={zone} onChange={setZone} className="h-8 w-44 text-xs" options={zoneOptions}
              placeholder={t("kbZone")} searchPlaceholder={t("search")} emptyText={t("pickNone")} />
          )}
          {(resp || zone) && <Button size="sm" variant="ghost" className="h-8 text-xs" onClick={() => { setResp(""); setZone(""); }}><X className="size-3.5" />{t("kbClear")}</Button>}
          <Segmented size="sm" value={sort} onChange={setSort} className="ml-auto" options={[
            { value: "used", label: t("kbSortUsed") }, { value: "images", label: t("kbSortImages") }, { value: "new", label: t("kbSortNew") },
          ]} />
        </div>
        <div className="flex flex-wrap gap-1.5">
          {([
            ["routing", t("kbFRouting"), Route, routingCount], ["images", t("kbFImages"), Images, undefined],
            ["variants", t("kbFVariants"), Shuffle, undefined], ["novariants", t("kbFNoVariants"), Shuffle, undefined],
            ["task", t("kbOnlyTask"), ListTodo, undefined],
          ] as [Flag, string, typeof Route, number | undefined][]).map(([f, label, Icon, n]) => (
            <button key={f} type="button" onClick={() => toggleFlag(f)}
              className={`inline-flex h-7 items-center gap-1.5 rounded-full border px-2.5 text-xs transition-colors ${flags.has(f) ? "border-primary bg-primary/10 text-primary" : "text-muted-foreground hover:text-foreground"}`}>
              <Icon className="size-3.5" />{label}{n != null && n > 0 && <span className="rounded-full bg-foreground/10 px-1.5 text-[10px] font-semibold">{n}</span>}
            </button>
          ))}
        </div>
        {flags.has("routing") && <p className="text-xs text-muted-foreground">{t("kbFRoutingHint")}</p>}
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
              <button key={e.id} type="button" onClick={() => (selecting ? toggleSel(e.id) : edit(e.id))}
                className={`group flex flex-col rounded-xl border bg-card text-left shadow-xs transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-md ${selecting && sel.has(e.id) ? "border-primary ring-2 ring-primary/30" : ""}`}>
                <div className="flex flex-1 flex-col gap-2 p-4">
                  <div className="flex items-center gap-1.5 text-xs">
                    <EntryBadge status={e.status} t={t} />
                    <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{t(`k_${e.kind}` as SKey)}</span>
                    {e.pending && <span className="rounded bg-warning/10 px-1.5 py-0.5 text-[11px] text-warning">{t("pendingEdit")}</span>}
                    {selecting && <span className={`grid size-4 place-items-center rounded border ${sel.has(e.id) ? "border-primary bg-primary text-primary-foreground" : ""}`}>{sel.has(e.id) && <Check className="size-3" />}</span>}
                    {e.answer_mode === "on" && <span className="rounded bg-success/10 px-1.5 py-0.5 text-[11px] text-success">{t("mode_on")}</span>}
                    {e.answer_mode === "off" && <span className="rounded bg-warning/10 px-1.5 py-0.5 text-[11px] text-warning">{t("mode_offL")}</span>}
                    {e.creates_task && <span className="inline-flex items-center gap-0.5 rounded bg-primary/10 px-1.5 py-0.5 text-[11px] text-primary"><ListTodo className="size-3" />{t("kbTask")}</span>}
                    {e.priority && <Star className="ml-auto size-4 fill-warning text-warning" />}
                  </div>
                  <span className="line-clamp-2 font-medium leading-snug group-hover:text-primary">{e.title}</span>
                  <p className="line-clamp-3 text-sm leading-relaxed text-muted-foreground">{e.answer.replace(/\*\*/g, "")}</p>
                </div>
                <div className="flex items-center gap-3 border-t px-4 py-2 text-xs text-muted-foreground">
                  {(e.attachments?.length ?? 0) > 0 && <span className="inline-flex items-center gap-0.5" title={t("attachments")}><Paperclip className="size-3" />{e.attachments.length}</span>}
                  {(e.image_examples_count ?? 0) > 0 && <span className="inline-flex items-center gap-0.5"><Images className="size-3" />{e.image_examples_count}</span>}
                  {e.ask_first && <span className="inline-flex items-center" title={t("askFirst")}><ListChecks className="size-3" /></span>}
                  {(e.variants?.length ?? 0) > 0 && <span className="inline-flex items-center gap-0.5" title={t("kbFVariants")}><Shuffle className="size-3" />{e.variants!.length}</span>}
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
