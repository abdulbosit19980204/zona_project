"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { Bot, Check, ChevronLeft, ChevronRight, Copy, ExternalLink, RotateCcw, GitMerge, Layers, ListChecks, MessageSquare, Pencil, Search, Sparkles, SquareStack, Star, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, type ClaudeKind, type Entry } from "./api";
import { EntryBadge, EntryPicker, fmtDate, OwnerSelect, Segmented, useSupportMutation } from "./common";
import { AISuggestions } from "./ai-suggestions";
import { BotAnswers } from "./bot-answers";
import { Duplicates } from "./duplicates";
import { Recheck } from "./recheck";
import { EntryEditor } from "./entry-editor";
import { MediaRow } from "./media";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";

type View = "queue" | "cards" | "clusters" | "dups" | "recheck" | "ai" | "answers";
const PAGE = 20;

export function SupportReview() {
  return <Suspense><ReviewInner /></Suspense>;
}

/** Tasdiqlash navbati: yangi javoblar va tasdiqlangan javoblarga kiritilgan tahrirlar — uch xil ko'rinishda. */
function ReviewInner() {
  const t = useSt();
  const params = useSearchParams();
  const [view, setView] = useState<View>(() => (params.get("view") as View) || "queue");
  const [editing, setEditing] = useState<number | null>(() => Number(params.get("entry")) || null);
  const [open, setOpen] = useState(() => !!Number(params.get("entry")));
  // navbat backend'da sahifalanadi (20 tadan): manba savollar va fayllar faqat ko'rinayotgan sahifa uchun keladi
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  const [cf, setCf] = useState<"" | "any" | Exclude<ClaudeKind, "">>("");
  const counts = useQuery({ queryKey: ["support", "entries", "claude-counts"], queryFn: supportApi.claudeCounts, staleTime: 30_000 });
  useEffect(() => { const h = setTimeout(() => { setSearch(q.trim()); setPage(0); }, 350); return () => clearTimeout(h); }, [q]);
  const fresh = useQuery({
    queryKey: ["support", "entries", "queue", page, search, cf],
    queryFn: () => supportApi.entriesPage({ status: "new,review", limit: PAGE, offset: page * PAGE, sources: 1,
      ...(search ? { q: search } : {}), ...(cf ? { claude: cf } : {}) }),
    placeholderData: keepPreviousData,
  });
  const edits = useQuery({ queryKey: ["support", "entries", "pending"], queryFn: () => supportApi.entries({ status: "approved", pending: 1 }) });
  // guruhlash uchun butun navbat kerak — faqat shu ko'rinish ochilganda (manbalarsiz, yengil)
  const all = useQuery({ queryKey: ["support", "entries", "queue-all"], queryFn: () => supportApi.entries({ status: "new,review" }),
    enabled: view === "clusters" });
  const total = fresh.data?.count ?? 0;
  const rv = useQuery({ queryKey: ["support", "reviews", "count"], queryFn: () => supportApi.reviews({ status: "open", limit: 1 }), staleTime: 30_000 });
  const openReviews = (rv.data?.counts.wrong ?? 0) + (rv.data?.counts.check ?? 0);
  const items = useMemo(() => [...(page === 0 && !search && !cf ? edits.data ?? [] : []), ...(fresh.data?.results ?? [])]
    .sort((a, b) => Number(b.priority) - Number(a.priority)), [fresh.data, edits.data, page, search, cf]);
  const cc = counts.data ?? {};
  const claudeSelect = (cc.any ?? 0) > 0 && (
    <label className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
      <Sparkles className="size-3.5 text-violet-500" />
      <select className="h-9 rounded-md border bg-background px-2 text-sm text-foreground" value={cf} aria-label={t("clTitle")}
        onChange={(e) => { setCf(e.target.value as typeof cf); setPage(0); }}>
        <option value="">{t("clTitle")}: {t("dtAll")}</option>
        <option value="any">{t("clAny")} ({cc.any})</option>
        <option value="same">{t("cl_same")} ({cc.same ?? 0})</option>
        <option value="general">{t("cl_general")} ({cc.general ?? 0})</option>
        <option value="status">{t("cl_status")} ({cc.status ?? 0})</option>
        <option value="handoff">{t("cl_handoff")} ({cc.handoff ?? 0})</option>
      </select>
    </label>
  );
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const edit = (id: number) => { setEditing(id); setOpen(true); };
  const pager = (
    <div className="mb-3 flex flex-wrap items-center gap-2">
      <div className="relative min-w-56 flex-1 sm:max-w-80">
        <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-9 pl-8" />
      </div>
      {claudeSelect}
      {cf && <span className="basis-full text-xs text-muted-foreground">{t(`clHint_${cf}` as SKey)}</span>}
      <span className="text-xs text-muted-foreground">
        {total ? `${page * PAGE + 1}–${Math.min(total, (page + 1) * PAGE)} / ${total}` : "0"}
        {fresh.isFetching && " …"}
      </span>
      <span className="ml-auto flex gap-1">
        <Button size="icon" variant="outline" className="size-8" aria-label={t("pgPrev")} disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft className="size-4" /></Button>
        <span className="self-center px-1 text-xs tabular-nums text-muted-foreground">{page + 1} / {pages}</span>
        <Button size="icon" variant="outline" className="size-8" aria-label={t("pgNext")} disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}><ChevronRight className="size-4" /></Button>
      </span>
    </div>
  );

  return (
    <SupportShell title={t("reviewTitle")} description={t("reviewDesc")}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented value={view} onChange={setView} options={[
          { value: "queue", label: t("viewQueue"), count: total + (edits.data?.length ?? 0), icon: ListChecks },
          { value: "cards", label: t("viewCards"), icon: SquareStack },
          { value: "clusters", label: t("viewClusters"), icon: Layers },
          { value: "dups", label: t("viewDups"), icon: Copy },
          { value: "recheck", label: t("viewRecheck"), icon: RotateCcw },
          { value: "ai", label: t("viewAI"), icon: Sparkles },
          { value: "answers", label: t("viewAnswers"), count: openReviews || undefined, icon: Bot },
        ]} />
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">{t(`viewHint_${view}` as SKey)}</p>
      </div>
      {view === "ai" && <AISuggestions t={t} />}
      {view === "answers" && <BotAnswers t={t} />}
      {view === "dups" && <Duplicates t={t} />}
      {view === "recheck" && <Recheck t={t} onEdit={edit} />}
      {(view === "queue" || view === "cards") && pager}
      {(view === "queue" || view === "cards") && (fresh.isLoading || edits.isLoading) && <Skeleton className="h-48" />}
      {(view === "queue" || view === "cards") && !fresh.isLoading && !edits.isLoading && items.length === 0 && <EmptyState icon={Check} title={t("queueEmpty")} />}
      {items.length > 0 && view === "queue" && <QueueView key={`${page}-${search}`} items={items} t={t} onEdit={edit} />}
      {items.length > 0 && view === "cards" && <CardsView key={`${page}-${search}`} items={items} t={t} />}
      {view === "clusters" && all.isLoading && <Skeleton className="h-48" />}
      {view === "clusters" && !!all.data?.length && <ClustersView items={all.data} t={t} onEdit={edit} />}
      {view === "clusters" && all.data?.length === 0 && <EmptyState icon={Check} title={t("queueEmpty")} />}
      <EntryEditor entryId={editing} open={open} onOpenChange={setOpen} />
    </SupportShell>
  );
}

function EntryHead({ e, t }: { e: Entry; t: ST }) {
  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
      {e.priority && <span className="inline-flex items-center gap-1 text-warning"><Star className="size-3.5 fill-warning" />{t("priority")}</span>}
      <EntryBadge status={e.status} t={t} />
      {e.pending && <Badge variant="outline" className="border-warning/50 font-normal text-warning">{t("pendingEdit")}</Badge>}
      <span>{t(`src_${e.source}` as SKey)}</span>
      <span>· {t("by")}: {e.pending?.by || e.author || "—"}</span>
      <span>· {fmtDate(e.pending?.at || e.created_at)}</span>
    </div>
  );
}

/** Yozuv qaysi savoldan o'rganilgan: muallif, guruh, matn va savoldagi BARCHA fayllar (albom, qo'shimcha skrinshotlar). */
function Sources({ e, t }: { e: Entry; t: ST }) {
  const src = e.sources_info ?? [];
  if (!src.length) return null;
  const title = (e.pending?.title ?? e.title).trim();
  return (
    <div className="grid gap-2">
      {src.map((s) => (
        <div key={s.id} className="grid min-w-0 gap-1.5 rounded-lg border bg-muted/30 p-2.5">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
            <MessageSquare className="size-3.5" />
            <span className="font-medium text-foreground">{t("srcTitle")}</span>
            {s.user && <span>· {s.user}</span>}
            {s.group && <span>· {s.group}</span>}
            <span>· {fmtDate(s.at)}</span>
            {s.media.length > 0 && <span>· {t("srcFiles", { n: s.media.length })}</span>}
            {s.link && (
              <a href={s.link} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-primary hover:underline">
                <ExternalLink className="size-3.5" />{t("srcOpen")}
              </a>
            )}
          </div>
          {s.text && s.text.trim() !== title && <p className="whitespace-pre-wrap break-words text-sm">{s.text}</p>}
          {s.info.length > 0 && (
            <p className="break-words text-xs text-muted-foreground"><span className="font-medium">{t("srcInfo")}:</span> {s.info.join(" · ")}</p>
          )}
          <MediaRow items={s.media} />
          {!s.text && s.ocr && <p className="line-clamp-2 break-words text-xs text-muted-foreground">{t("srcOcr")}: {s.ocr}</p>}
        </div>
      ))}
    </div>
  );
}

function Diff({ e, t }: { e: Entry; t: ST }) {
  if (!e.pending?.answer) return <p className="whitespace-pre-wrap text-sm">{e.answer}</p>;
  return (
    <div className="grid gap-2 sm:grid-cols-2">
      <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-sm">
        <div className="mb-1 text-xs text-muted-foreground">{t("oldAnswer")}</div><p className="whitespace-pre-wrap">{e.answer}</p>
      </div>
      <div className="rounded-lg border border-success/30 bg-success/5 p-2 text-sm">
        <div className="mb-1 text-xs text-muted-foreground">{t("newAnswer")}</div><p className="whitespace-pre-wrap">{e.pending.answer}</p>
      </div>
    </div>
  );
}

/* ---------------------------------------------------------------- 1. navbat (ro'yxat, ommaviy) */
/** Claude nima qilgani: holat xabari / uzatish almashtirildi, standart javobga mos, umumlashtirilgan. */
function ClaudeNote({ e, t }: { e: Entry; t: ST }) {
  const can = useCan();
  const one = useSupportMutation(() => supportApi.bulk([e.id], "absorb"), t("clAbsorbed"));
  if (!e.claude_kind) return null;
  return (
    <div className="flex flex-wrap items-center gap-2 rounded-lg border border-violet-500/30 bg-violet-500/[0.05] px-2.5 py-1.5 text-xs">
      <Badge variant="outline" className="gap-1 border-violet-500/40 font-normal text-violet-600 dark:text-violet-400">
        <Sparkles className="size-3" />{t(`cl_${e.claude_kind}` as SKey)}
      </Badge>
      <span className="min-w-0 flex-1 text-muted-foreground">{e.claude_note}
        {e.claude_kind === "general" && !!e.claude_covers_count && <> · {t("clCovers", { n: e.claude_covers_count })}</>}
      </span>
      {can.edit && e.claude_target && e.claude_kind !== "general" && (
        <Button size="sm" variant="outline" className="h-6 px-2 text-xs" disabled={one.isPending} onClick={() => one.mutate(undefined)}>
          <GitMerge className="size-3.5" />{t("clAbsorb")}
        </Button>
      )}
    </div>
  );
}

/** Savol kimga tegishli: mas'ul (belgilash va eslatmalar uchun) — shu yerning o'zida almashtiriladi. */
function Owner({ e, t }: { e: Entry; t: ST }) {
  const can = useCan();
  const save = useSupportMutation((id: number | null) => supportApi.updateEntry(e.id, { responsible: id }), t("saved"));
  const [picking, setPicking] = useState(false);
  const tg = e.responsible_tg ?? [];
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="text-muted-foreground">{t("owner")}:</span>
      {can.edit && picking ? (
        <OwnerSelect t={t} value={e.responsible} disabled={save.isPending}
          onChange={(id) => save.mutate(id, { onSuccess: () => setPicking(false) })} className="h-7 text-xs" />
      ) : (
        <span className="font-medium">{e.responsible_name || t("ownerNone")}</span>
      )}
      {can.edit && !picking && (
        <button type="button" className="text-xs text-primary hover:underline" onClick={() => setPicking(true)}>{t("ownerChange")}</button>
      )}
      {tg.length > 0 && <span className="text-xs text-primary">{tg.map((x) => "@" + x).join(" ")}</span>}
    </div>
  );
}

function QueueView({ items, t, onEdit }: { items: Entry[]; t: ST; onEdit: (id: number) => void }) {
  const can = useCan();
  const [sel, setSel] = useState<Set<number>>(new Set());
  const bulk = useSupportMutation((a: "approve" | "reject" | "absorb") => supportApi.bulk([...sel], a), (r) => t("bulkDone", { n: r.done }));
  const one = useSupportMutation((fn: () => Promise<unknown>) => fn(), t("saved"));
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const all = sel.size === items.length;
  // klaviatura: ↓/J — keyingi, ↑/K — oldingi, A — tasdiqlash, R — rad, S — standartga qo'shish, E — tahrir
  const [active, setActive] = useState(0);
  const cur = items[Math.min(active, items.length - 1)];
  useEffect(() => {
    if (!can.edit) return;
    const onKey = (ev: KeyboardEvent) => {
      const el = ev.target as HTMLElement | null;
      if (ev.ctrlKey || ev.metaKey || ev.altKey || (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName)))) return;
      if (document.querySelector("[role=dialog]")) return;
      const k = ev.key.toLowerCase();
      const go = (d: number) => { ev.preventDefault(); setActive((i) => Math.max(0, Math.min(items.length - 1, i + d))); };
      if (k === "arrowdown" || k === "j") go(1);
      else if (k === "arrowup" || k === "k") go(-1);
      else if (!cur || one.isPending) return;
      else if (k === "a") { ev.preventDefault(); one.mutate(() => supportApi.approve(cur.id)); }
      else if (k === "r") { ev.preventDefault(); one.mutate(() => supportApi.reject(cur.id)); }
      else if (k === "s" && cur.claude_target) { ev.preventDefault(); one.mutate(() => supportApi.bulk([cur.id], "absorb")); }
      else if (k === "e") { ev.preventDefault(); onEdit(cur.id); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [can.edit, cur, items.length, one, onEdit]);
  useEffect(() => {
    if (cur) document.getElementById(`rv-${cur.id}`)?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [cur]);

  return (
    <div className="grid gap-3">
      {can.edit && (
        <Card className="sticky top-0 z-10 flex-row flex-wrap items-center gap-2 bg-card/95 p-2.5 shadow-sm backdrop-blur">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={all ? true : sel.size ? "indeterminate" : false} onCheckedChange={() => setSel(all ? new Set() : new Set(items.map((e) => e.id)))} />
            {sel.size ? t("selected", { n: sel.size }) : t("selectAll", { n: items.length })}
          </label>
          <Button size="sm" disabled={!sel.size || bulk.isPending} onClick={() => bulk.mutate("approve", { onSuccess: () => setSel(new Set()) })}>
            <Check className="size-4" />{t("approveSelected")}
          </Button>
          <Button size="sm" variant="outline" disabled={!sel.size || bulk.isPending} onClick={() => bulk.mutate("reject", { onSuccess: () => setSel(new Set()) })}>
            <X className="size-4" />{t("rejectSelected")}
          </Button>
          <span className="ml-auto hidden text-[11px] text-muted-foreground lg:inline">{t("rvKeys")}</span>
          {items.some((e) => sel.has(e.id) && e.claude_target) && (
            <Button size="sm" variant="outline" className="border-violet-500/40 text-violet-600 dark:text-violet-400" disabled={bulk.isPending}
              onClick={() => bulk.mutate("absorb", { onSuccess: () => setSel(new Set()) })} title={t("clAbsorbHint")}>
              <GitMerge className="size-4" />{t("clAbsorbSel")}
            </Button>
          )}
        </Card>
      )}
      {items.map((e) => (
        <Card key={e.id} id={`rv-${e.id}`} onClick={() => setActive(items.indexOf(e))}
          className={cn("gap-2 p-4 transition-colors", sel.has(e.id) && "border-primary/50 bg-primary/[0.03]",
            cur?.id === e.id && can.edit && "ring-2 ring-primary/40")}>
          <div className="flex items-start gap-3">
            {can.edit && <Checkbox className="mt-1" checked={sel.has(e.id)} onCheckedChange={() => toggle(e.id)} />}
            <div className="grid min-w-0 flex-1 gap-2">
              <EntryHead e={e} t={t} />
              <div className="font-semibold leading-snug">{e.pending?.title ?? e.title}</div>
              {(e.questions ?? []).length > 1 && <div className="text-xs text-muted-foreground">{e.questions.slice(1).join(" · ")}</div>}
              <Sources e={e} t={t} />
              <Diff e={e} t={t} />
              <ClaudeNote e={e} t={t} />
              <Owner e={e} t={t} />
              <div className="flex flex-wrap gap-2 border-t pt-3">
                {can.edit && <Button size="sm" onClick={() => one.mutate(() => supportApi.approve(e.id))}><Check className="size-4" />{t("approve")}</Button>}
                {can.edit && <Button size="sm" variant="outline" onClick={() => one.mutate(() => supportApi.reject(e.id))}><X className="size-4" />{t("reject")}</Button>}
                <Button size="sm" variant="ghost" onClick={() => onEdit(e.id)}><Pencil className="size-4" />{t("edit")}</Button>
              </div>
            </div>
          </div>
        </Card>
      ))}
    </div>
  );
}

/* ---------------------------------------------------------------- 2. kartochka (bittalab, tez) */
function CardsView({ items, t }: { items: Entry[]; t: ST }) {
  const [i, setI] = useState(0);
  const e = items[Math.min(i, items.length - 1)];
  if (!e) return null;
  return <OneCard key={`${e.id}-${e.updated_at}`} e={e} t={t} pos={Math.min(i, items.length - 1) + 1} total={items.length}
    next={() => setI((i + 1) % items.length)} />;
}

function OneCard({ e, t, pos, total, next }: { e: Entry; t: ST; pos: number; total: number; next: () => void }) {
  const can = useCan();
  const [answer, setAnswer] = useState(e.pending?.answer ?? e.answer);
  const [target, setTarget] = useState("");
  const approved = useQuery({ queryKey: ["support", "entries", "brief", "approved"], queryFn: () => supportApi.entriesBrief("approved"),
    staleTime: 60_000 });
  const act = useSupportMutation((fn: () => Promise<unknown>) => fn(), t("saved"));
  const changed = answer.trim() !== (e.pending?.answer ?? e.answer);
  const approve = () => act.mutate(async () => {
    if (changed) await supportApi.updateEntry(e.id, { answer: answer.trim() });
    return supportApi.approve(e.id);
  });

  return (
    <Card className="mx-auto w-full max-w-3xl gap-3 p-5">
      <div className="flex items-center justify-between text-xs text-muted-foreground">
        <span>{t("cardOf", { i: pos, n: total })}</span>
        <Button size="sm" variant="ghost" onClick={next}>{t("skip")}<ChevronRight className="size-4" /></Button>
      </div>
      <EntryHead e={e} t={t} />
      <div className="text-lg font-semibold">{e.pending?.title ?? e.title}</div>
      {e.questions.length > 0 && <ul className="list-disc pl-5 text-sm text-muted-foreground">{e.questions.map((q, k) => <li key={k} className="whitespace-pre-wrap">{q}</li>)}</ul>}
      <Sources e={e} t={t} />
      {e.pending?.answer && <div className="rounded-lg border p-2 text-sm"><div className="text-xs text-muted-foreground">{t("oldAnswer")}</div><p className="whitespace-pre-wrap">{e.answer}</p></div>}
      <Textarea rows={7} value={answer} onChange={(x) => setAnswer(x.target.value)} disabled={!can.edit} />
      {can.edit && (
        <div className="flex flex-wrap gap-2">
          <Button disabled={answer.trim().length < 2 || act.isPending} onClick={approve}><Check className="size-4" />{t("approve")}</Button>
          <Button variant="outline" disabled={act.isPending} onClick={() => act.mutate(() => supportApi.reject(e.id))}><X className="size-4" />{t("reject")}</Button>
        </div>
      )}
      {can.edit && !e.pending && (
        <div className="grid gap-2 rounded-lg border p-3">
          <div className="flex items-center gap-1.5 text-sm font-medium"><GitMerge className="size-4" />{t("mergeInto")}</div>
          <p className="text-xs text-muted-foreground">{t("mergeHint")}</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <EntryPicker value={target} onChange={setTarget} className="flex-1"
              options={(approved.data ?? []).filter((x) => x.id !== e.id).map((x) => ({ id: x.id, title: x.title }))}
              placeholder={t("chooseTarget")} searchPlaceholder={t("pickSearch")} emptyText={t("pickNone")} />
            <Button variant="outline" disabled={!target || act.isPending} onClick={() => act.mutate(() => supportApi.merge(e.id, Number(target)))}>
              <GitMerge className="size-4" />{t("mergeInto")}
            </Button>
          </div>
        </div>
      )}
    </Card>
  );
}

/* ---------------------------------------------------------------- 3. guruhlangan (o'xshash savollar) */
function words(s: string) {
  return new Set(s.toLowerCase().replace(/[ʻʼ’'`]/g, "").split(/[^\p{L}\p{N}]+/u).filter((w) => w.length >= 4).map((w) => w.slice(0, 6)));
}

function clusters(items: Entry[]) {
  const sets = items.map((e) => words([e.title, ...e.questions].join(" ")));
  const used = new Set<number>();
  const out: Entry[][] = [];
  items.forEach((e, i) => {
    if (used.has(i)) return;
    used.add(i);
    const group = [e];
    items.forEach((f, j) => {
      if (used.has(j)) return;
      const a = sets[i], b = sets[j];
      const inter = [...a].filter((w) => b.has(w)).length;
      if (inter / Math.max(1, Math.min(a.size, b.size)) >= 0.5) { group.push(f); used.add(j); }
    });
    out.push(group);
  });
  return out.sort((a, b) => b.length - a.length);
}

function ClustersView({ items, t, onEdit }: { items: Entry[]; t: ST; onEdit: (id: number) => void }) {
  const can = useCan();
  const groups = useMemo(() => clusters(items), [items]);
  const act = useSupportMutation(async (g: Entry[]) => {
    await supportApi.approve(g[0].id);
    for (const e of g.slice(1)) await supportApi.merge(e.id, g[0].id);
  }, t("merged"));
  return (
    <div className="grid gap-3">
      {groups.map((g) => (
        <Card key={g[0].id} className="gap-2 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className="font-normal">{t("clusterN", { n: g.length })}</Badge>
            <span className="font-medium">{g[0].title}</span>
          </div>
          <ul className="grid gap-1 text-sm">
            {g.map((e) => (
              <li key={e.id} className="flex items-start gap-2">
                <button className="min-w-0 flex-1 truncate text-left hover:text-primary" onClick={() => onEdit(e.id)}>
                  <span className="text-muted-foreground">{e.author || "—"}:</span> {e.answer}
                </button>
              </li>
            ))}
          </ul>
          {can.edit && (
            <Button size="sm" className="justify-self-start" disabled={act.isPending} onClick={() => act.mutate(g)}>
              <Check className="size-4" />{g.length > 1 ? t("approveCluster") : t("approve")}
            </Button>
          )}
        </Card>
      ))}
    </div>
  );
}
