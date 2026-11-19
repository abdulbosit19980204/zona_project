"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, ChevronRight, Copy, GitMerge, Layers, ListChecks, Pencil, Sparkles, SquareStack, Star, X } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense, useMemo, useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Skeleton } from "@/components/ui/skeleton";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";

import { supportApi, type Entry } from "./api";
import { EntryBadge, EntryPicker, fmtDate, Segmented, useSupportMutation } from "./common";
import { AISuggestions } from "./ai-suggestions";
import { Duplicates } from "./duplicates";
import { EntryEditor } from "./entry-editor";
import { useSt, type SKey, type ST } from "./i18n";
import { SupportShell } from "./shell";

type View = "queue" | "cards" | "clusters" | "dups" | "ai";

export function SupportReview() {
  return <Suspense><ReviewInner /></Suspense>;
}

/** Tasdiqlash navbati: yangi javoblar va tasdiqlangan javoblarga kiritilgan tahrirlar — uch xil ko'rinishda. */
function ReviewInner() {
  const t = useSt();
  const params = useSearchParams();
  const [view, setView] = useState<View>("queue");
  const [editing, setEditing] = useState<number | null>(() => Number(params.get("entry")) || null);
  const [open, setOpen] = useState(() => !!Number(params.get("entry")));
  const fresh = useQuery({ queryKey: ["support", "entries", "queue"], queryFn: () => supportApi.entries({ status: "new,review" }) });
  const edits = useQuery({ queryKey: ["support", "entries", "pending"], queryFn: () => supportApi.entries({ status: "approved", pending: 1 }) });
  const items = useMemo(() => [...(edits.data ?? []), ...(fresh.data ?? [])]
    .sort((a, b) => Number(b.priority) - Number(a.priority)), [fresh.data, edits.data]);
  const edit = (id: number) => { setEditing(id); setOpen(true); };

  return (
    <SupportShell title={t("reviewTitle")} description={t("reviewDesc")}>
      <div className="mb-4 flex flex-wrap items-center gap-3">
        <Segmented value={view} onChange={setView} options={[
          { value: "queue", label: t("viewQueue"), count: items.length, icon: ListChecks },
          { value: "cards", label: t("viewCards"), icon: SquareStack },
          { value: "clusters", label: t("viewClusters"), icon: Layers },
          { value: "dups", label: t("viewDups"), icon: Copy },
          { value: "ai", label: t("viewAI"), icon: Sparkles },
        ]} />
        <p className="min-w-0 flex-1 text-xs text-muted-foreground">{t(`viewHint_${view}` as SKey)}</p>
      </div>
      {view === "ai" && <AISuggestions t={t} />}
      {view === "dups" && <Duplicates t={t} />}
      {view !== "ai" && view !== "dups" && (fresh.isLoading || edits.isLoading) && <Skeleton className="h-48" />}
      {view !== "ai" && view !== "dups" && !fresh.isLoading && !edits.isLoading && items.length === 0 && <EmptyState icon={Check} title={t("queueEmpty")} />}
      {items.length > 0 && view === "queue" && <QueueView items={items} t={t} onEdit={edit} />}
      {items.length > 0 && view === "cards" && <CardsView items={items} t={t} />}
      {items.length > 0 && view === "clusters" && <ClustersView items={items.filter((e) => !e.pending)} t={t} onEdit={edit} />}
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
function QueueView({ items, t, onEdit }: { items: Entry[]; t: ST; onEdit: (id: number) => void }) {
  const can = useCan();
  const [sel, setSel] = useState<Set<number>>(new Set());
  const bulk = useSupportMutation((a: "approve" | "reject") => supportApi.bulk([...sel], a), (r) => t("bulkDone", { n: r.done }));
  const one = useSupportMutation((fn: () => Promise<unknown>) => fn(), t("saved"));
  const toggle = (id: number) => setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const all = sel.size === items.length;

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
        </Card>
      )}
      {items.map((e) => (
        <Card key={e.id} className={`gap-2 p-4 transition-colors ${sel.has(e.id) ? "border-primary/50 bg-primary/[0.03]" : ""}`}>
          <div className="flex items-start gap-3">
            {can.edit && <Checkbox className="mt-1" checked={sel.has(e.id)} onCheckedChange={() => toggle(e.id)} />}
            <div className="grid min-w-0 flex-1 gap-2">
              <EntryHead e={e} t={t} />
              <div className="font-semibold leading-snug">{e.pending?.title ?? e.title}</div>
              {(e.questions ?? []).length > 1 && <div className="text-xs text-muted-foreground">{e.questions.slice(1).join(" · ")}</div>}
              <Diff e={e} t={t} />
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
  const approved = useQuery({ queryKey: ["support", "entries", "approved-all"], queryFn: () => supportApi.entries({ status: "approved" }) });
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
