"use client";

import { useQuery } from "@tanstack/react-query";
import { Check, Copy, GitMerge, ListPlus, Loader2, Sparkles, Wand2, X } from "lucide-react";
import { useState } from "react";

import { EmptyState } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";

import { supportApi, type AISuggestion } from "./api";
import { fmtDate, useSupportMutation } from "./common";
import type { SKey, ST } from "./i18n";

/** AI takliflari: bilim bazasini va javobsiz savollarni AI tahlil qiladi, xodim tasdiqlaydi (tahrirlab ham). */
export function AISuggestions({ t }: { t: ST }) {
  const can = useCan();
  const jobs = useQuery({
    queryKey: ["support", "ai-jobs"], queryFn: supportApi.aiJobs,
    refetchInterval: (q) => ((q.state.data ?? []).some((j) => j.status === "queued" || j.status === "running") ? 4000 : 30_000),
  });
  const list = useQuery({ queryKey: ["support", "ai-suggestions"], queryFn: () => supportApi.aiSuggestions("pending"), refetchInterval: 15_000 });
  const start = useSupportMutation((kind: "entries" | "unanswered" | "dedupe") => supportApi.startAIJob(kind), t("aiJobStarted"));
  const jobLabel = (k: string) => t(k === "entries" ? "aiReviewKb" : k === "dedupe" ? "aiReviewDedupe" : "aiReviewUnanswered");
  const running = (jobs.data ?? []).find((j) => j.status === "queued" || j.status === "running");

  return (
    <div className="grid gap-4">
      <Card className="gap-3 p-4">
        <div className="flex items-center gap-2 text-sm font-semibold"><Sparkles className="size-4 text-primary" />{t("aiTitle")}</div>
        <p className="text-sm text-muted-foreground">{t("aiDesc")}</p>
        {can.edit && (
          <div className="flex flex-wrap gap-2">
            <Button disabled={!!running || start.isPending} onClick={() => start.mutate("entries")}><Wand2 className="size-4" />{t("aiReviewKb")}</Button>
            <Button variant="outline" disabled={!!running || start.isPending} onClick={() => start.mutate("unanswered")}><ListPlus className="size-4" />{t("aiReviewUnanswered")}</Button>
            <Button variant="outline" disabled={!!running || start.isPending} onClick={() => start.mutate("dedupe")}><Copy className="size-4" />{t("aiReviewDedupe")}</Button>
          </div>
        )}
        {running && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            {jobLabel(running.kind)} · {running.progress.done ?? 0}/{running.progress.total ?? "…"} · {t("aiFound", { n: running.progress.suggestions ?? 0 })}
          </div>
        )}
        {(jobs.data ?? []).filter((j) => j.status !== "queued" && j.status !== "running").slice(0, 3).map((j) => (
          <div key={j.id} className="text-xs text-muted-foreground">
            {fmtDate(j.finished_at || j.created_at)} · {jobLabel(j.kind)} · {t("aiFound", { n: j.progress.suggestions ?? 0 })}
            {j.error && <span className="text-destructive"> · {j.error}</span>}
          </div>
        ))}
      </Card>

      {list.data?.length === 0 && <EmptyState icon={Sparkles} title={t("aiNone")} hint={t("aiNoneHint")} />}
      <div className="grid gap-3">
        {list.data?.map((s) => <SuggestionCard key={s.id} s={s} t={t} />)}
      </div>
    </div>
  );
}

const KIND_ICON = { improve: Wand2, questions: ListPlus, merge: GitMerge, new: Sparkles, archive: X, dedupe: Copy } as const;

function SuggestionCard({ s, t }: { s: AISuggestion; t: ST }) {
  const can = useCan();
  const [answer, setAnswer] = useState(s.payload.answer ?? "");
  const decide = useSupportMutation((action: "approve" | "reject") =>
    supportApi.decideSuggestion(s.id, action, action === "approve" && (s.kind === "improve" || s.kind === "new" || s.kind === "dedupe") ? { answer } : undefined), t("saved"));
  const Icon = KIND_ICON[s.kind];

  return (
    <Card className="gap-3 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge className="gap-1 font-normal"><Icon className="size-3" />{t(`sg_${s.kind}` as SKey)}</Badge>
        <span className="font-medium">{s.entry_title || s.payload.title}</span>
        {s.target_title && <span className="text-sm text-muted-foreground">→ {s.target_title}</span>}
        <span className="ml-auto text-xs text-muted-foreground">{fmtDate(s.created_at)}</span>
      </div>
      {s.reason && <p className="rounded-lg bg-muted/50 p-2 text-sm"><b>{t("aiWhy")}:</b> {s.reason}</p>}

      {(s.kind === "improve" || s.kind === "new") && (
        <div className="grid gap-2 md:grid-cols-2">
          {s.current && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-2 text-sm">
              <div className="mb-1 text-xs text-muted-foreground">{t("oldAnswer")}</div><p className="whitespace-pre-wrap">{s.current.answer}</p>
            </div>
          )}
          <div className={s.current ? "" : "md:col-span-2"}>
            <div className="mb-1 text-xs text-muted-foreground">{t("newAnswer")}{s.kind === "new" && !s.payload.answer ? ` — ${t("aiWriteAnswer")}` : ""}</div>
            <Textarea rows={6} value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={!can.edit} className="border-success/40" />
          </div>
        </div>
      )}
      {s.kind === "dedupe" && (
        <div className="grid gap-2">
          <div className="text-xs text-muted-foreground">{t("dupWillArchive", { n: (s.group ?? []).length })}</div>
          <ul className="grid gap-1.5">
            {(s.group ?? []).map((g) => (
              <li key={g.id} className="rounded-lg border border-dashed p-2 text-sm">
                <div className="font-medium">{g.title}</div>
                <p className="line-clamp-2 text-xs text-muted-foreground">{g.answer}</p>
              </li>
            ))}
          </ul>
          <div className="text-xs text-muted-foreground">{t("dupFinal")}</div>
          <Textarea rows={5} value={answer} onChange={(e) => setAnswer(e.target.value)} disabled={!can.edit} className="border-success/40" />
        </div>
      )}
      {s.kind === "new" && (s.payload.questions ?? []).length > 0 && (
        <p className="text-xs text-muted-foreground">{t("questions")}: {s.payload.questions!.join(" · ")}</p>
      )}
      {s.kind === "merge" && s.current && (
        <div className="grid gap-2 md:grid-cols-2">
          <div className="rounded-lg border border-dashed p-2 text-sm">
            <div className="mb-1 text-xs text-muted-foreground">{t("sgMergeFrom")}: {s.entry_title}</div>
            <p className="line-clamp-5 whitespace-pre-wrap">{s.current.answer}</p>
          </div>
          <div className="rounded-lg border border-success/30 bg-success/5 p-2 text-sm">
            <div className="mb-1 text-xs text-muted-foreground">{t("sgMergeInto")}: {s.target_title}</div>
            <p className="line-clamp-5 whitespace-pre-wrap">{s.target_answer}</p>
          </div>
        </div>
      )}
      {s.kind === "questions" && (
        <div className="flex flex-wrap gap-1.5">{(s.payload.questions ?? []).map((q) => <Badge key={q} variant="outline" className="font-normal">+ {q}</Badge>)}</div>
      )}
      {s.payload.ask_first && s.kind !== "questions" && <p className="text-xs text-muted-foreground">{t("askFirst")}: {s.payload.ask_first}</p>}

      {can.edit && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={decide.isPending || ((s.kind === "new" || s.kind === "improve" || s.kind === "dedupe") && answer.trim().length < 2)}
            onClick={() => decide.mutate("approve")}><Check className="size-4" />{t("approve")}</Button>
          <Button size="sm" variant="outline" disabled={decide.isPending} onClick={() => decide.mutate("reject")}><X className="size-4" />{t("reject")}</Button>
        </div>
      )}
    </Card>
  );
}
