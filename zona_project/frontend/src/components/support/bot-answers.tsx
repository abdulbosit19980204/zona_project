"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { AlertTriangle, Bot, Check, ChevronLeft, ChevronRight, ExternalLink, Search, Send, ThumbsDown, ThumbsUp, Undo2 } from "lucide-react";
import { useEffect, useState } from "react";

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

import { supportApi, type ReviewRow } from "./api";
import { fmtDate, Segmented, useSupportMutation } from "./common";
import type { SKey, ST } from "./i18n";
import { MediaRow } from "./media";

type Status = "open" | "wrong" | "check" | "fixed" | "ok" | "none" | "all";
const PAGE = 20;

/** Bot javoblari: xato deb belgilanganlar (xodim ⚠️ yoki 👎), tekshirish kerak bo'lganlar (👍), tuzatilganlar.
 * To'g'ri javob yoziladi va bitta tugma bilan guruhdagi bot javobiga reply qilib yuboriladi (xohlasa — bilim bazasiga ham). */
export function BotAnswers({ t }: { t: ST }) {
  const [status, setStatus] = useState<Status>("open");
  const [page, setPage] = useState(0);
  const [q, setQ] = useState("");
  const [search, setSearch] = useState("");
  useEffect(() => { const h = setTimeout(() => { setSearch(q.trim()); setPage(0); }, 350); return () => clearTimeout(h); }, [q]);
  const list = useQuery({
    queryKey: ["support", "reviews", status, page, search],
    queryFn: () => supportApi.reviews({ status, limit: PAGE, offset: page * PAGE, ...(search ? { q: search } : {}) }),
    placeholderData: keepPreviousData,
  });
  const c = list.data?.counts ?? {};
  const total = list.data?.count ?? 0;
  const pages = Math.max(1, Math.ceil(total / PAGE));
  const pick = (s: Status) => { setStatus(s); setPage(0); };

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <Segmented size="sm" value={status} onChange={pick} options={[
          { value: "open", label: t("rvOpen"), count: (c.wrong ?? 0) + (c.check ?? 0) },
          { value: "wrong", label: t("rvWrong"), count: c.wrong, icon: AlertTriangle },
          { value: "check", label: t("rvCheck"), count: c.check, icon: ThumbsUp },
          { value: "fixed", label: t("rvFixed"), count: c.fixed, icon: Check },
          { value: "ok", label: t("rvOk"), count: c.ok },
          { value: "none", label: t("rvNone"), count: c.none },
          { value: "all", label: t("all") },
        ]} />
        <div className="relative min-w-56 flex-1 sm:max-w-72">
          <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-9 pl-8" />
        </div>
        <span className="ml-auto flex items-center gap-1 text-xs text-muted-foreground">
          {total ? `${page * PAGE + 1}–${Math.min(total, (page + 1) * PAGE)} / ${total}` : "0"}{list.isFetching && " …"}
          <Button size="icon" variant="outline" className="ml-1 size-8" aria-label={t("pgPrev")} disabled={page === 0} onClick={() => setPage(page - 1)}><ChevronLeft className="size-4" /></Button>
          <Button size="icon" variant="outline" className="size-8" aria-label={t("pgNext")} disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}><ChevronRight className="size-4" /></Button>
        </span>
      </div>
      <p className="text-xs text-muted-foreground">{t(`rvHint_${status}` as SKey)}</p>
      {list.isLoading && <Skeleton className="h-48" />}
      {list.data?.results.length === 0 && <EmptyState icon={Bot} title={t("rvEmpty")} />}
      {list.data?.results.map((r) => <ReviewCard key={`${r.id}-${r.review}-${r.fixed_at}`} r={r} t={t} />)}
    </div>
  );
}

function ReviewCard({ r, t }: { r: ReviewRow; t: ST }) {
  const can = useCan();
  const [text, setText] = useState(r.fixed_text || "");
  const [send, setSend] = useState(true);  // tuzatilgan javob ham guruhdagi o'sha xabarda yangilanadi
  const [learn, setLearn] = useState(true);
  const act = useSupportMutation((body: Parameters<typeof supportApi.reviewAction>[1]) => supportApi.reviewAction(r.id, body),
    (x) => (x.kb_entry ? t("rvFixedKb") : t("saved")));
  const tone = r.review === "wrong" ? "border-destructive/40" : r.review === "check" ? "border-warning/40" : r.review === "fixed" ? "border-success/40" : "";
  const badge = r.review ? (
    <Badge variant="outline" className={cn("font-normal", r.review === "wrong" ? "border-destructive/50 text-destructive"
      : r.review === "check" ? "border-warning/50 text-warning" : "border-success/50 text-success")}>{t(`rv_${r.review}` as SKey)}</Badge>
  ) : <Badge variant="outline" className="font-normal">{t("rv_")}</Badge>;
  return (
    <Card className={cn("gap-3 p-4", tone)}>
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
        {badge}
        {r.hidden && <Badge variant="outline" className="border-warning/50 font-normal text-warning" title={t("rvHiddenHint")}>{t("rvHidden")}</Badge>}
        {r.feedback > 0 && <span className="inline-flex items-center gap-1"><ThumbsUp className="size-3.5" />{t("rvAskerLiked")}</span>}
        {r.feedback < 0 && <span className="inline-flex items-center gap-1 text-destructive"><ThumbsDown className="size-3.5" />{t("rvAskerDisliked")}</span>}
        {r.review_by && <span>· {r.review_by}{r.review_at ? ` · ${fmtDate(r.review_at)}` : ""}</span>}
        <span>· {r.user || "—"}</span>
        {r.group && <span>· {r.group}</span>}
        <span>· {fmtDate(r.at)}</span>
        {r.link && <a href={r.link} target="_blank" rel="noreferrer" className="ml-auto inline-flex items-center gap-1 text-primary hover:underline">
          <ExternalLink className="size-3.5" />{t("srcOpen")}</a>}
      </div>
      <div className="grid gap-3 lg:grid-cols-2">
        <div className="grid min-w-0 gap-2">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{t("rvQuestion")}</div>
          {r.text ? <p className="whitespace-pre-wrap break-words text-sm">{r.text}</p> : <p className="text-sm text-muted-foreground">{r.problem || t("photo")}</p>}
          <MediaRow items={r.media} />
          {!r.text && r.ocr && <p className="line-clamp-3 break-words text-xs text-muted-foreground">{t("srcOcr")}: {r.ocr}</p>}
        </div>
        <div className="grid min-w-0 gap-2">
          <div className="flex items-center gap-2 text-[11px] uppercase tracking-wide text-muted-foreground">
            <Bot className="size-3.5" />{t("rvBotAnswer")}{r.entry_title && <span className="normal-case tracking-normal">· {r.entry_title}</span>}
          </div>
          <p className={cn("whitespace-pre-wrap break-words rounded-lg bg-muted/40 p-2.5 text-sm", r.review === "wrong" && "line-through decoration-destructive/40")}>
            {r.answer_text || "—"}</p>
          {r.fixed_text && r.review !== "fixed" && (
            <div className="rounded-lg border border-destructive/30 bg-destructive/5 p-2.5 text-sm">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-destructive">{t("rvPrevFix")}</div>
              <p className="whitespace-pre-wrap break-words line-through decoration-destructive/40">{r.fixed_text}</p>
              <div className="mt-1 text-xs text-muted-foreground">{r.fixed_by}{r.fixed_at ? ` · ${fmtDate(r.fixed_at)}` : ""}</div>
            </div>
          )}
          {r.fixed_text && r.review === "fixed" && (
            <div className="rounded-lg border border-success/30 bg-success/5 p-2.5 text-sm">
              <div className="mb-1 text-[11px] uppercase tracking-wide text-success">{t("rvFixedAnswer")}{r.sent && ` · ${t("rvSent")}`}</div>
              <p className="whitespace-pre-wrap break-words">{r.fixed_text}</p>
              <div className="mt-1 text-xs text-muted-foreground">{r.fixed_by}{r.fixed_at ? ` · ${fmtDate(r.fixed_at)}` : ""}</div>
            </div>
          )}
        </div>
      </div>
      {can.edit && (
        <div className="grid gap-2 border-t pt-3">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder={t("rvCorrectPh")} />
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
            <label className="flex items-center gap-2"><Checkbox checked={send} onCheckedChange={(v) => setSend(!!v)} />{t("rvSendToGroup")}</label>
            <label className="flex items-center gap-2"><Checkbox checked={learn} onCheckedChange={(v) => setLearn(!!v)} />{t("rvAddKb")}</label>
            <span className="ml-auto flex flex-wrap gap-1.5">
              {r.review !== "ok" && <Button size="sm" variant="outline" disabled={act.isPending} onClick={() => act.mutate({ action: "ok" })}>
                <Check className="size-4" />{t("rvMarkOk")}</Button>}
              {r.review !== "wrong" && <Button size="sm" variant="outline" className="text-destructive" disabled={act.isPending}
                onClick={() => act.mutate({ action: "wrong" })}><AlertTriangle className="size-4" />{t("rvMarkWrong")}</Button>}
              {r.review && <Button size="sm" variant="ghost" disabled={act.isPending} onClick={() => act.mutate({ action: "clear" })}>
                <Undo2 className="size-4" />{t("rvClear")}</Button>}
              <Button size="sm" disabled={!text.trim() || act.isPending}
                onClick={() => act.mutate({ action: "fix", text: text.trim(), send, learn })}>
                <Send className="size-4" />{r.fixed_text ? t("rvRefix") : send ? t("rvFixSend") : t("rvFixSave")}</Button>
            </span>
          </div>
        </div>
      )}
    </Card>
  );
}
