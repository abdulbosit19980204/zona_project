"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, CheckCheck, Image as ImageIcon, Inbox, MessageSquareReply, Search, Send, ThumbsDown, ThumbsUp, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";

import { EmptyState, StatCard } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, type MsgStatus, type SupportMessage } from "./api";
import { fmtDate, MsgBadge, stageLabel, useSupportMutation } from "./common";
import { useSt, type SKey, type ST } from "./i18n";
import { MediaRow } from "./media";
import { SupportShell } from "./shell";

type Filter = "open" | MsgStatus | "all";
const FILTERS: Filter[] = ["open", "escalated", "drafted", "answered", "closed", "all"];
const STATUS_DOT: Record<MsgStatus, string> = {
  new: "bg-primary", escalated: "bg-warning", drafted: "bg-violet-500", answered: "bg-success", closed: "bg-muted-foreground/40",
  ignored: "bg-muted-foreground/40",
};

/** Guruh savollari: chapda ro'yxat (filtr, qidiruv), o'ngda suhbat ko'rinishidagi zanjir va javob yozish. */
export function SupportInbox() {
  const t = useSt();
  const [filter, setFilter] = useState<Filter>("open");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const status = filter === "open" ? "escalated,drafted,new" : filter;
  const stats = useQuery({ queryKey: ["support", "stats"], queryFn: () => supportApi.stats(7), refetchInterval: 30_000 });
  const list = useQuery({
    queryKey: ["support", "messages", status, q],
    queryFn: () => supportApi.messages({ status, ...(q ? { q } : {}), limit: 200 }),
    refetchInterval: 15_000,
  });
  const s = stats.data;
  const botClosed = ["template", "faq", "rule", "ai", "image"].reduce((n, k) => n + (s?.by_stage[k] ?? 0), 0);
  const current = useMemo(() => list.data?.find((m) => m.id === selected) ?? null, [list.data, selected]);

  return (
    <SupportShell title={t("inboxTitle")} description={t("inboxDesc2")}>
      <div className="mb-4 grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatCard label={t("kpiTotal")} value={s?.total ?? "—"} icon={Inbox} />
        <StatCard label={t("kpiBot")} value={botClosed} icon={Bot} tone="success" />
        <StatCard label={t("kpiHuman")} value={s?.by_status.escalated ?? 0} icon={UserRound} tone="warning" />
        <Link href="/support/review" className="rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <StatCard label={t("kpiQueue")} value={(s?.entries.new ?? 0) + (s?.entries.review ?? 0) + (s?.pending_edits ?? 0)} icon={CheckCheck} />
        </Link>
      </div>

      <Card className="grid min-h-[60vh] gap-0 overflow-hidden p-0 lg:h-[calc(100vh-330px)] lg:grid-cols-[minmax(300px,380px)_1fr]">
        {/* ro'yxat */}
        <div className={cn("flex min-h-0 flex-col border-r", current && "hidden lg:flex")}>
          <div className="grid gap-2 border-b p-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-9 pl-8" />
            </div>
            <div className="flex flex-wrap gap-1">
              {FILTERS.map((f) => (
                <button key={f} type="button" onClick={() => { setFilter(f); setSelected(null); }}
                  className={cn("rounded-full border px-2.5 py-1 text-xs transition-colors",
                    filter === f ? "border-primary bg-primary text-primary-foreground" : "hover:bg-muted")}>
                  {f === "open" ? t("needsAnswer") : f === "all" ? t("all") : t(`m_${f}` as SKey)}
                </button>
              ))}
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {list.isLoading && <div className="grid gap-2 p-3">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-14" />)}</div>}
            {list.data?.length === 0 && <div className="p-6"><EmptyState icon={Inbox} title={t("inboxEmpty")} hint={t("inboxEmptyHint")} /></div>}
            {list.data?.map((m) => (
              <button key={m.id} type="button" onClick={() => setSelected(m.id)}
                className={cn("flex w-full gap-3 border-b px-3 py-2.5 text-left transition-colors hover:bg-muted/60",
                  selected === m.id && "bg-primary/5")}>
                <span className="relative grid size-9 shrink-0 place-items-center rounded-full bg-muted text-sm font-semibold uppercase">
                  {(m.user_name || "?").slice(0, 1)}
                  <span className={cn("absolute -bottom-0.5 -right-0.5 size-2.5 rounded-full ring-2 ring-card", STATUS_DOT[m.status])} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className="truncate text-sm font-medium">{m.user_name || "—"}</span>
                    <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{fmtDate(m.created_at)}</span>
                  </span>
                  <span className="flex items-center gap-1 truncate text-xs text-muted-foreground">
                    {m.has_photo && <ImageIcon className="size-3 shrink-0" />}
                    <span className="truncate">{m.text || m.ocr_text || t("photo")}</span>
                  </span>
                  <span className="block truncate text-[11px] text-muted-foreground/80">{m.group_title}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* suhbat */}
        <div className={cn("flex min-h-0 flex-col", !current && "hidden lg:flex")}>
          {current ? <Conversation key={current.id} m={current} t={t} onBack={() => setSelected(null)} />
            : <div className="grid flex-1 place-items-center p-8 text-center text-sm text-muted-foreground">{t("pickQuestion")}</div>}
        </div>
      </Card>
    </SupportShell>
  );
}

function Bubble({ side, tone, who, at, children }: {
  side: "left" | "right"; tone?: "bot" | "staff" | "clarify" | "info"; who: string; at?: string; children: ReactNode;
}) {
  return (
    <div className={cn("flex", side === "right" ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm shadow-sm",
        side === "left" ? "rounded-tl-sm bg-card" : "rounded-tr-sm",
        tone === "bot" && "border border-primary/30 bg-primary/10",
        tone === "staff" && "bg-success/15",
        tone === "clarify" && "border border-warning/40 bg-warning/10",
        tone === "info" && "bg-card")}>
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          <span className="font-medium text-foreground/80">{who}</span>{at && <span>· {fmtDate(at)}</span>}
        </div>
        {children}
      </div>
    </div>
  );
}

function Conversation({ m, t, onBack }: { m: SupportMessage; t: ST; onBack: () => void }) {
  const can = useCan();
  const [text, setText] = useState("");
  const [save, setSave] = useState(true);
  const [approve, setApprove] = useState(false);
  const answer = useSupportMutation(() => supportApi.answer(m.id, text, save, approve), t("sent"));
  const close = useSupportMutation(() => supportApi.close(m.id));
  const done = m.status === "answered" || m.status === "closed";
  const botSaid = m.answer_text && m.stage !== "panel";
  const send = () => answer.mutate(undefined, { onSuccess: () => setText("") });

  return (
    <>
      <div className="flex items-center gap-2 border-b px-4 py-3">
        <Button size="icon" variant="ghost" className="lg:hidden" onClick={onBack} aria-label={t("back")}><ArrowLeft className="size-4" /></Button>
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{m.user_name}{m.user_username && <span className="font-normal text-muted-foreground"> · @{m.user_username}</span>}</div>
          <div className="truncate text-xs text-muted-foreground">{m.group_title}</div>
        </div>
        <MsgBadge status={m.status} t={t} />
        {m.feedback === 1 && <ThumbsUp className="size-4 text-success" />}
        {m.feedback === -1 && <ThumbsDown className="size-4 text-destructive" />}
        {!done && <Button size="sm" variant="ghost" disabled={close.isPending} onClick={() => close.mutate(undefined)}><X className="size-4" />{t("closeQ")}</Button>}
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-muted/30 p-4">
        <Bubble side="left" who={m.user_name || "—"} at={m.created_at}>
          {m.text && <p className="whitespace-pre-wrap">{m.text}</p>}
          <MediaRow items={m.media} />
          {m.ocr_text && <details className="mt-1 text-xs text-muted-foreground"><summary className="cursor-pointer">{t("ocr")}</summary><p className="mt-1 whitespace-pre-wrap">{m.ocr_text}</p></details>}
        </Bubble>
        {m.staff_answers.map((a, i) => (
          <Bubble key={i} side={a.kind === "info" ? "left" : "right"} tone={a.kind === "staff" ? "staff" : a.kind}
            who={`${a.by} · ${t(`k_${a.kind}` as SKey)}`} at={a.at}>
            <p className="whitespace-pre-wrap">{a.text}</p>
            <MediaRow items={a.media} />
          </Bubble>
        ))}
        {botSaid && (
          <Bubble side="right" tone="bot"
            who={`${m.status === "answered" && m.answered_by === "bot" ? t("botAnswered") : t("botDraft")}${m.stage ? ` · ${stageLabel(m.stage, t)}` : ""}${m.confidence ? ` · ${m.confidence}%` : ""}`}>
            <p className="whitespace-pre-wrap">{m.answer_text}</p>
            {m.entry_title && <Link className="mt-1 inline-block text-xs text-primary hover:underline" href={`/support/knowledge?entry=${m.entry}`}>{m.entry_title}</Link>}
            {!done && <div className="mt-2"><Button size="sm" variant="outline" onClick={() => setText(m.answer_text)}>{t("useDraft")}</Button></div>}
          </Bubble>
        )}
        {m.stage === "panel" && m.answer_text && (
          <Bubble side="right" tone="staff" who={`${m.answered_by} · ${t("s_panel")}`} at={m.answered_at ?? undefined}>
            <p className="whitespace-pre-wrap">{m.answer_text}</p>
          </Bubble>
        )}
      </div>

      {!done ? (
        <div className="grid gap-2 border-t p-3">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder={t("answerPlaceholder")}
            onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim().length > 1) send(); }} />
          <div className="flex flex-wrap items-center gap-4">
            <label className="flex items-center gap-2 text-xs"><Switch checked={save} onCheckedChange={setSave} />{t("saveToKb")}</label>
            {can.edit && save && <label className="flex items-center gap-2 text-xs"><Switch checked={approve} onCheckedChange={setApprove} />{t("approveNow")}</label>}
            <span className="hidden text-[11px] text-muted-foreground sm:inline">Ctrl + Enter</span>
            <Button className="ml-auto" disabled={text.trim().length < 2 || answer.isPending} onClick={send}>
              <Send className="size-4" />{t("send")}
            </Button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 border-t p-3 text-xs text-muted-foreground"><MessageSquareReply className="size-4" />{t("threadDone")}</div>
      )}
    </>
  );
}
