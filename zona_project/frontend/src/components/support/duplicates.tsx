"use client";

import { useQuery } from "@tanstack/react-query";
import { Archive, Check, Copy, Crown, EyeOff, Loader2, Search, Sparkles, ThumbsDown, ThumbsUp, Wand2, Zap } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/common/page";
import { ConfirmDialog } from "@/components/qrdrive/common";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, type DedupeDecision, type DupGroup } from "./api";
import { EntryBadge, Segmented, useSupportMutation } from "./common";
import type { SKey, ST } from "./i18n";
import { smartFilter } from "./smart-search";

const LEVELS = ["70", "80", "90"] as const;

/**
 * Takrorlarni tozalash: bir savolga yozilgan bir nechta javob bitta guruhda. Eng yaxshisi (sifat bahosi bo'yicha) toj
 * bilan belgilangan; birlashtirilganda qolganlari arxivga tushadi (o'chirilmaydi), savol ko'rinishlari va rasmlar saqlanadi.
 */
export function Duplicates({ t }: { t: ST }) {
  const can = useCan();
  const [level, setLevel] = useState<(typeof LEVELS)[number]>("80");
  const [q, setQ] = useState("");
  const [hidden, setHidden] = useState<Set<number>>(new Set());
  const [autoOpen, setAutoOpen] = useState(false);
  const [aiOpen, setAiOpen] = useState(false);
  const [aiAuto, setAiAuto] = useState(false);
  const list = useQuery({ queryKey: ["support", "duplicates", level], queryFn: () => supportApi.duplicates(Number(level)) });
  const jobs = useQuery({
    queryKey: ["support", "ai-jobs"], queryFn: supportApi.aiJobs,
    refetchInterval: (x) => ((x.state.data ?? []).some((j) => j.status === "queued" || j.status === "running") ? 4000 : 30_000),
  });
  const preview = useQuery({ queryKey: ["support", "dedupe-preview"], queryFn: () => supportApi.dedupeAuto(92, true), enabled: autoOpen && can.edit });
  const auto = useSupportMutation(() => supportApi.dedupeAuto(92), (r) => t("dupAutoDone", { n: r.merged }));
  const ai = useSupportMutation(() => supportApi.startAIJob("dedupe", { threshold: Number(level), auto: aiAuto }), t("aiJobStarted"));
  const running = (jobs.data ?? []).find((j) => j.kind === "dedupe" && (j.status === "queued" || j.status === "running"));
  const lastDone = (jobs.data ?? []).find((j) => j.kind === "dedupe" && j.status !== "queued" && j.status !== "running");
  const groups = useMemo(() => smartFilter((list.data?.groups ?? []).filter((g) => !hidden.has(g.keep)), q,
    (g) => g.entries.map((e) => `${e.title} ${e.answer}`).join(" ")), [list.data, hidden, q]);

  return (
    <div className="grid gap-4">
      <div className="grid gap-3 rounded-xl border bg-card p-3 shadow-xs">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-xs text-muted-foreground">{t("dupLevel")}</span>
          <Segmented size="sm" value={level} onChange={setLevel}
            options={LEVELS.map((l) => ({ value: l, label: `≥ ${l}%` }))} />
          {list.data && <span className="text-xs text-muted-foreground">{t("dupSummary", { g: list.data.total, n: list.data.entries })}</span>}
          {can.edit && (
            <div className="ml-auto flex flex-wrap gap-2">
              <Button size="sm" variant="outline" onClick={() => setAutoOpen(true)}><Zap className="size-4" />{t("dupAuto")}</Button>
              <Button size="sm" disabled={!!running} onClick={() => setAiOpen(true)}><Sparkles className="size-4" />{t("dupAi")}</Button>
            </div>
          )}
        </div>
        <div className="relative">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("dupSearch")} className="h-9 bg-muted/40 pl-8" />
        </div>
        {running && (
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Loader2 className="size-3.5 animate-spin" />{t("dupAiRunning", { d: running.progress.done ?? 0, n: running.progress.total ?? "…" })}
            · {t("aiFound", { n: running.progress.suggestions ?? 0 })}
          </div>
        )}
        {!running && lastDone && (
          <div className="text-xs text-muted-foreground">
            {t("dupAiLast", { n: lastDone.progress.suggestions ?? 0, a: lastDone.progress.applied ?? 0 })}
            {lastDone.error && <span className="text-destructive"> · {lastDone.error}</span>}
          </div>
        )}
      </div>

      {list.isLoading && <div className="grid gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-48" />)}</div>}
      {list.data && groups.length === 0 && <EmptyState icon={Check} title={t("dupNone")} hint={t("dupNoneHint")} />}
      {groups.map((g) => (
        <GroupCard key={`${g.keep}-${g.entries.map((e) => e.id).join("-")}`} g={g} t={t} onHide={() => setHidden(new Set([...hidden, g.keep]))} />
      ))}

      <ConfirmDialog open={autoOpen} onOpenChange={setAutoOpen} title={t("dupAutoTitle")}
        description={preview.data ? t("dupAutoConfirm", { g: preview.data.groups, n: preview.data.merged }) : t("loading")}
        confirmLabel={t("dupAutoGo")} pending={auto.isPending}
        onConfirm={() => auto.mutate(undefined, { onSuccess: () => setAutoOpen(false) })} />

      <Dialog open={aiOpen} onOpenChange={setAiOpen}>
        <DialogContent className="max-w-lg">
          <DialogHeader><DialogTitle className="flex items-center gap-2"><Sparkles className="size-4 text-primary" />{t("dupAi")}</DialogTitle></DialogHeader>
          <p className="text-sm text-muted-foreground">{t("dupAiHint", { l: level })}</p>
          <label className="flex items-start gap-3 rounded-lg border p-3 text-sm">
            <Switch checked={aiAuto} onCheckedChange={setAiAuto} className="mt-0.5" />
            <span><span className="font-medium">{t("dupAiAuto")}</span><span className="mt-0.5 block text-xs text-muted-foreground">{t("dupAiAutoHint")}</span></span>
          </label>
          <Button disabled={ai.isPending} onClick={() => ai.mutate(undefined, { onSuccess: () => setAiOpen(false) })}>
            <Wand2 className="size-4" />{aiAuto ? t("dupAiGoAuto") : t("dupAiGo")}
          </Button>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function GroupCard({ g, t, onHide }: { g: DupGroup; t: ST; onHide: () => void }) {
  const can = useCan();
  const [keep, setKeep] = useState(g.keep);
  const [include, setInclude] = useState<Set<number>>(() => new Set(g.entries.map((e) => e.id)));
  const keepRow = g.entries.find((e) => e.id === keep)!;
  const [answer, setAnswer] = useState(keepRow.answer);
  const [edited, setEdited] = useState(false);
  const [ai, setAi] = useState<DedupeDecision | null>(null);
  const merge = useSupportMutation(() => supportApi.dedupeMerge({
    keep, merge: [...include].filter((id) => id !== keep), ...(edited || ai ? { answer: answer.trim() } : {}),
    ...(ai?.answer_ru ? { answer_ru: ai.answer_ru } : {}),
  }), (r) => t("dupMerged", { n: r.merged }));
  const compose = useSupportMutation(() => supportApi.dedupeCompose(g.entries.map((e) => e.id)));
  const pickKeep = (id: number) => {
    setKeep(id);
    setInclude(new Set([...include, id]));
    if (!edited && !ai) setAnswer(g.entries.find((e) => e.id === id)!.answer);
  };
  const toMerge = [...include].filter((id) => id !== keep).length;

  return (
    <div className="overflow-hidden rounded-xl border bg-card shadow-xs">
      <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-4 py-2.5">
        <Copy className="size-4 text-muted-foreground" />
        <span className="text-sm font-medium">{t("dupGroupN", { n: g.entries.length })}</span>
        <Badge variant="outline" className={cn("font-mono font-normal", g.similarity >= 90 ? "border-destructive/40 text-destructive" : "border-warning/40 text-warning")}>
          {g.similarity}%
        </Badge>
        <Button size="sm" variant="ghost" className="ml-auto h-7 text-xs" onClick={onHide}><EyeOff className="size-3.5" />{t("dupNotDup")}</Button>
      </div>

      <div className="divide-y">
        {g.entries.map((e) => {
          const isKeep = e.id === keep;
          const inc = include.has(e.id);
          return (
            <div key={e.id} className={cn("flex gap-3 px-4 py-3 transition-colors", isKeep && "bg-success/[0.06]", !inc && "opacity-50")}>
              {can.edit && (
                <Checkbox className="mt-1" checked={inc} disabled={isKeep} aria-label={t("dupInclude")}
                  onCheckedChange={() => setInclude((s) => { const n = new Set(s); if (n.has(e.id)) n.delete(e.id); else n.add(e.id); return n; })} />
              )}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-1.5">
                  {isKeep && <span className="inline-flex items-center gap-1 rounded bg-success/15 px-1.5 py-0.5 text-[11px] font-medium text-success"><Crown className="size-3" />{t("dupKeep")}</span>}
                  {e.best && !isKeep && <span className="rounded bg-muted px-1.5 py-0.5 text-[11px] text-muted-foreground">{t("dupBest")}</span>}
                  <span className="font-medium leading-snug">{e.title}</span>
                </div>
                <p className="mt-1 line-clamp-3 whitespace-pre-wrap text-sm text-muted-foreground">{e.answer}</p>
                <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                  <EntryBadge status={e.status} t={t} />
                  <span className="inline-flex items-center gap-1.5" title={t("dupQuality")}>
                    <span className="h-1.5 w-14 overflow-hidden rounded-full bg-muted">
                      <span className={cn("block h-full rounded-full", e.quality >= 60 ? "bg-success" : e.quality >= 35 ? "bg-warning" : "bg-destructive")} style={{ width: `${e.quality}%` }} />
                    </span>
                    {e.quality}
                  </span>
                  {!isKeep && <span>{t("dupQSim")}: {e.question_sim}% · {t("dupASim")}: {e.answer_sim}%</span>}
                  <span>{e.uses}×</span>
                  <span className="inline-flex items-center gap-0.5"><ThumbsUp className="size-3" />{e.likes}</span>
                  <span className="inline-flex items-center gap-0.5"><ThumbsDown className="size-3" />{e.dislikes}</span>
                  {e.reasons.map((r) => <span key={r} className="rounded bg-muted px-1.5 py-px">{t(`dupR_${r}` as SKey)}</span>)}
                  {e.author && <span>· {e.author}</span>}
                </div>
              </div>
              {can.edit && !isKeep && (
                <Button size="sm" variant="outline" className="h-8 shrink-0 self-start" onClick={() => pickKeep(e.id)}>
                  <Crown className="size-3.5" />{t("dupMakeKeep")}
                </Button>
              )}
            </div>
          );
        })}
      </div>

      {can.edit && (
        <div className="grid gap-2 border-t bg-muted/20 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-sm font-medium">{t("dupFinal")}</span>
            {ai && <Badge variant="outline" className="gap-1 border-primary/40 font-normal text-primary"><Sparkles className="size-3" />AI</Badge>}
            <Button size="sm" variant="ghost" className="ml-auto h-7 text-xs" disabled={compose.isPending}
              onClick={() => compose.mutate(undefined, {
                onSuccess: (r) => {
                  setAi(r);
                  if (r.answer) setAnswer(r.answer);
                  if (r.keep) setKeep(r.keep);
                  if (r.merge.length) setInclude(new Set([...(r.keep ? [r.keep] : []), ...r.merge]));
                },
              })}>
              {compose.isPending ? <Loader2 className="size-3.5 animate-spin" /> : <Wand2 className="size-3.5" />}{t("dupCompose")}
            </Button>
          </div>
          {ai?.reason && <p className={cn("rounded-lg p-2 text-xs", ai.same ? "bg-primary/5" : "bg-warning/10 text-warning")}>{!ai.same && `${t("dupAiNotSame")} `}{ai.reason}</p>}
          <Textarea rows={5} value={answer} onChange={(e) => { setAnswer(e.target.value); setEdited(true); }} className="bg-background" />
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={!toMerge || answer.trim().length < 2 || merge.isPending} onClick={() => merge.mutate(undefined)}>
              <Check className="size-4" />{t("dupMergeBtn", { n: toMerge })}
            </Button>
            <span className="inline-flex items-center gap-1 text-xs text-muted-foreground"><Archive className="size-3.5" />{t("dupSafe")}</span>
          </div>
        </div>
      )}
    </div>
  );
}
