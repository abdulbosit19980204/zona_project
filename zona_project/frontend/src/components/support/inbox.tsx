"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot, BookOpen, CheckCheck, CircleCheck, CircleX, ExternalLink, Hourglass, Image as ImageIcon, Inbox, MessageSquareReply, Search, Send, Sparkles, ThumbsDown, ThumbsUp, UserRound, Users, X } from "lucide-react";
import Link from "next/link";
import { useMemo, useState, type ReactNode } from "react";

import { EmptyState } from "@/components/common/page";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";
import { cn } from "@/lib/utils";

import { supportApi, SYS_APPS, SYS_CATEGORIES, SYS_ORIGINS, type MsgStatus, type Resolution, type SupportMessage } from "./api";
import { fmtDate, Initials, Metric, MsgBadge, Segmented, stageLabel, useSupportMutation } from "./common";
import { useSt, type SKey, type ST } from "./i18n";
import { MediaRow } from "./media";
import { SupportShell } from "./shell";
import { smartFilter } from "./smart-search";

type Filter = "open" | MsgStatus | "all";
type ResFilter = "any" | "open" | "yes" | "no" | "asked";

/** Savol yakuni belgisi: hal bo'ldi / hal bo'lmadi / tasdiq kutilmoqda (noma'lum bo'lsa — hech narsa). */
function ResolutionMark({ r, t, label = false }: { r: Resolution; t: ST; label?: boolean }) {
  if (!r) return label ? <span className="text-muted-foreground">{t("r_")}</span> : null;
  const Icon = r === "yes" ? CircleCheck : r === "no" ? CircleX : Hourglass;
  const tone = r === "yes" ? "text-success" : r === "no" ? "text-destructive" : "text-warning";
  return (
    <span className={cn("inline-flex items-center gap-1", tone)} title={t(`r_${r}` as SKey)}>
      <Icon className="size-3.5 shrink-0" />{label && <span>{t(`r_${r}` as SKey)}</span>}
    </span>
  );
}
const STATUS_DOT: Record<MsgStatus, string> = {
  new: "bg-primary", escalated: "bg-warning", drafted: "bg-violet-500", answered: "bg-success", closed: "bg-muted-foreground/40",
  ignored: "bg-muted-foreground/40",
};

/** Guruh savollari: chapda ro'yxat, o'rtada suhbat va javob yozish, keng ekranda o'ngda tafsilotlar. */
export function SupportInbox() {
  const t = useSt();
  const [filter, setFilter] = useState<Filter>("open");
  const [res, setRes] = useState<ResFilter>("any");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const status = filter === "open" ? "escalated,drafted,new" : filter;
  const stats = useQuery({ queryKey: ["support", "stats"], queryFn: () => supportApi.stats(7), refetchInterval: 30_000 });
  const list = useQuery({
    queryKey: ["support", "messages", status, res],
    queryFn: () => supportApi.messages({ status, limit: 300, ...(res === "any" ? {} : { resolution: res }) }),
    refetchInterval: 15_000,
  });
  const shown = useMemo(() => (list.data ? smartFilter(list.data, q,
    (m) => `${m.user_name} ${m.user_username} ${m.group_title} ${m.problem} ${m.text} ${m.ocr_text} ${m.entry_title}`) : undefined), [list.data, q]);
  const s = stats.data;
  const bs = s?.by_status ?? {};
  const botClosed = ["template", "faq", "rule", "ai", "image"].reduce((n, k) => n + (s?.by_stage[k] ?? 0), 0);
  const current = useMemo(() => shown?.find((m) => m.id === selected) ?? null, [shown, selected]);
  const queue = (s?.entries.new ?? 0) + (s?.entries.review ?? 0) + (s?.pending_edits ?? 0);

  return (
    <SupportShell title={t("inboxTitle")} description={t("inboxDesc2")} fill>
      <div className="mb-4 grid shrink-0 grid-cols-2 gap-3 xl:grid-cols-4">
        <Metric label={t("kpiTotal")} value={s?.total ?? "—"} hint={t("last7")} icon={Inbox} tone="primary" />
        <Metric label={t("kpiBot")} value={botClosed} hint={s?.total ? `${Math.round((100 * botClosed) / s.total)}%` : undefined} icon={Bot} tone="success" />
        <Metric label={t("kpiHuman")} value={bs.escalated ?? 0} icon={UserRound} tone="warning" />
        <Link href="/support/review" className="rounded-xl outline-none transition-transform hover:-translate-y-0.5 focus-visible:ring-2 focus-visible:ring-ring">
          <Metric label={t("kpiQueue")} value={queue} hint={t("openReview")} icon={CheckCheck} />
        </Link>
      </div>

      <div className="grid min-h-[560px] flex-1 overflow-hidden rounded-xl border bg-card shadow-xs lg:grid-cols-[minmax(300px,360px)_1fr] 2xl:grid-cols-[360px_1fr_300px]">
        {/* ro'yxat */}
        <div className={cn("flex min-h-0 flex-col border-r", current && "hidden lg:flex")}>
          <div className="grid gap-2.5 border-b p-3">
            <div className="relative">
              <Search className="absolute left-2.5 top-2.5 size-4 text-muted-foreground" />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-9 bg-muted/40 pl-8" />
            </div>
            <Segmented size="sm" value={filter} onChange={(f) => { setFilter(f); setSelected(null); }} className="w-full" options={[
              { value: "open", label: t("needsAnswer"), count: (bs.escalated ?? 0) + (bs.drafted ?? 0) + (bs.new ?? 0) },
              { value: "escalated", label: t("m_escalated"), count: bs.escalated },
              { value: "drafted", label: t("m_drafted"), count: bs.drafted },
              { value: "answered", label: t("m_answered") },
              { value: "closed", label: t("m_closed") },
              { value: "all", label: t("all") },
            ]} />
            <Segmented size="sm" value={res} onChange={(v) => { setRes(v); setSelected(null); }} className="w-full" options={[
              { value: "any", label: t("r_any") },
              { value: "open", label: t("r_open") },
              { value: "asked", label: t("r_asked"), icon: Hourglass },
              { value: "yes", label: t("r_yes"), icon: CircleCheck },
              { value: "no", label: t("r_no"), icon: CircleX },
            ]} />
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">
            {list.isLoading && <div className="grid gap-2 p-3">{[0, 1, 2, 3, 4].map((i) => <Skeleton key={i} className="h-16" />)}</div>}
            {shown?.length === 0 && <div className="p-6"><EmptyState icon={Inbox} title={t("inboxEmpty")} hint={t("inboxEmptyHint")} /></div>}
            {shown?.map((m) => (
              <button key={m.id} type="button" onClick={() => setSelected(m.id)}
                className={cn("relative flex w-full gap-3 border-b px-3 py-3 text-left transition-colors hover:bg-muted/50",
                  selected === m.id && "bg-primary/[0.06] before:absolute before:inset-y-0 before:left-0 before:w-0.5 before:bg-primary")}>
                <span className="relative">
                  <Initials name={m.user_name} />
                  <span className={cn("absolute -bottom-0.5 -right-0.5 size-3 rounded-full ring-2 ring-card", STATUS_DOT[m.status])} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline gap-2">
                    <span className="truncate text-sm font-medium">{m.user_name || "—"}</span>
                    <ResolutionMark r={m.resolution} t={t} />
                    <span className="ml-auto shrink-0 text-[11px] tabular-nums text-muted-foreground">{fmtDate(m.created_at)}</span>
                  </span>
                  <span className="mt-0.5 line-clamp-2 text-xs leading-snug text-muted-foreground">
                    {m.has_photo && <ImageIcon className="mr-1 inline size-3 -translate-y-px" />}
                    {m.text || m.ocr_text || t("photo")}
                  </span>
                  <span className="mt-1 flex items-center gap-1.5 text-[11px] text-muted-foreground/80">
                    <Users className="size-3 shrink-0" /><span className="truncate">{m.group_title}</span>
                    {m.stage && <span className="ml-auto shrink-0 rounded bg-muted px-1.5 py-px">{stageLabel(m.stage, t)}</span>}
                  </span>
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* suhbat */}
        <div className={cn("flex min-h-0 flex-col", !current && "hidden lg:flex")}>
          {current ? <Conversation key={current.id} m={current} t={t} onBack={() => setSelected(null)} />
            : (
              <div className="grid flex-1 place-items-center p-8 text-center">
                <div className="grid justify-items-center gap-3">
                  <span className="grid size-14 place-items-center rounded-2xl bg-muted text-muted-foreground"><MessageSquareReply className="size-6" /></span>
                  <p className="max-w-xs text-sm text-muted-foreground">{t("pickQuestion")}</p>
                </div>
              </div>
            )}
        </div>

        {/* tafsilotlar */}
        <aside className="hidden min-h-0 overflow-y-auto border-l bg-muted/20 2xl:block">
          {current ? <Details m={current} t={t} /> : <div className="p-5 text-xs text-muted-foreground">{t("detailsEmpty")}</div>}
        </aside>
      </div>
    </SupportShell>
  );
}

/** Tizim belgisi: ilova (qayerda ko'rindi), manba (xato qayerdan), toifa; xodim tuzatsa — eng ishonchli belgi bo'ladi. */
function SystemLabel({ m, t }: { m: SupportMessage; t: ST }) {
  const can = useCan();
  const save = useSupportMutation((body: Parameters<typeof supportApi.setLabel>[1]) => supportApi.setLabel(m.id, body), t("saved"));
  const sel = (field: "app" | "origin" | "category", opts: readonly string[], prefix: string) => (
    <select className="h-7 rounded-md border bg-background px-1.5 text-xs disabled:opacity-70" value={m[field]}
      disabled={!can.edit || save.isPending} aria-label={t(`lbl_${field}` as SKey)}
      onChange={(e) => save.mutate({ [field]: e.target.value } as Parameters<typeof supportApi.setLabel>[1])}>
      <option value="">{t(`lbl_${field}` as SKey)}: —</option>
      {opts.map((o) => <option key={o} value={o}>{t(`lbl_${field}` as SKey)}: {t(`${prefix}${o}` as SKey)}</option>)}
    </select>
  );
  return (
    <span className="grid gap-1.5">
      <span className="flex flex-wrap gap-1">
        {sel("app", SYS_APPS, "sys_")}{sel("origin", SYS_ORIGINS, "org_")}{sel("category", SYS_CATEGORIES, "cat_")}
      </span>
      <span className="text-[11px] text-muted-foreground">
        {m.labeled_by ? t(`lb_${m.labeled_by}` as SKey) : t("lb_none")}
        {m.train != null && ` · ${m.train ? t("trainYes") : t("trainNo")}`}
      </span>
      {m.solution && <span className="text-xs"><b className="text-muted-foreground">{t("dSolution")}:</b> {m.solution}</span>}
    </span>
  );
}

function Details({ m, t }: { m: SupportMessage; t: ST }) {
  const row = (label: string, value: ReactNode) => (
    <div className="grid gap-0.5 border-b py-2.5 last:border-b-0">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="text-sm">{value || "—"}</div>
    </div>
  );
  return (
    <div className="p-4">
      <div className="mb-3 flex items-center gap-3">
        <Initials name={m.user_name} className="size-11 text-sm" />
        <div className="min-w-0">
          <div className="truncate font-medium">{m.user_name || "—"}</div>
          {m.user_username && <a className="text-xs text-primary hover:underline" href={`https://t.me/${m.user_username}`} target="_blank" rel="noreferrer">@{m.user_username}</a>}
        </div>
      </div>
      <div className="rounded-lg border bg-card px-3">
        {row(t("dStatus"), <MsgBadge status={m.status} t={t} />)}
        {m.problem && row(t("dProblem"), m.problem)}
        {row(t("dResolution"), <span className="inline-flex flex-wrap items-center gap-1">
          <ResolutionMark r={m.resolution} t={t} label />
          {m.resolved_at && <span className="text-xs text-muted-foreground">· {fmtDate(m.resolved_at)}{m.resolved_by ? ` · ${m.resolved_by}` : ""}</span>}
        </span>)}
        {row(t("dSystem"), <SystemLabel m={m} t={t} />)}
        {row(t("dGroup"), m.group_title)}
        {row(t("dAsked"), fmtDate(m.created_at))}
        {m.answered_at && row(t("dAnswered"), `${fmtDate(m.answered_at)}${m.answered_by ? ` · ${m.answered_by}` : ""}`)}
        {m.stage && row(t("dStage"), `${stageLabel(m.stage, t)}${m.confidence ? ` · ${m.confidence}%` : ""}`)}
        {m.entry_title && row(t("dEntry"), <Link className="text-primary hover:underline" href={`/support/knowledge?entry=${m.entry}`}>{m.entry_title}</Link>)}
        {m.staff_answers.length > 0 && row(t("staffAnswers"), m.staff_answers.length)}
        {m.task && row(t("dTask"), <span className={m.task.status === "sent" ? "text-success" : m.task.status === "failed" ? "text-destructive" : "text-muted-foreground"}>
          {t(`ts_${m.task.status}` as SKey)} · @{m.task.assignee}{m.task.reply ? ` · ${m.task.reply.slice(0, 80)}` : ""}</span>)}
      </div>
      {m.link && (
        <Button variant="outline" size="sm" className="mt-3 w-full" asChild>
          <a href={m.link} target="_blank" rel="noreferrer"><ExternalLink className="size-4" />{t("openInTelegram")}</a>
        </Button>
      )}
    </div>
  );
}

function Bubble({ side, tone, who, at, icon, children }: {
  side: "left" | "right"; tone?: "bot" | "staff" | "clarify" | "info"; who: string; at?: string; icon?: ReactNode; children: ReactNode;
}) {
  return (
    <div className={cn("flex", side === "right" ? "justify-end" : "justify-start")}>
      <div className={cn("max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm shadow-xs",
        side === "left" ? "rounded-tl-md border bg-card" : "rounded-tr-md",
        tone === "bot" && "border border-primary/25 bg-primary/[0.08]",
        tone === "staff" && "border border-success/25 bg-success/10",
        tone === "clarify" && "border border-warning/35 bg-warning/10",
        tone === "info" && "bg-card")}>
        <div className="mb-1 flex flex-wrap items-center gap-1.5 text-[11px] text-muted-foreground">
          {icon}<span className="font-medium text-foreground/80">{who}</span>{at && <span>· {fmtDate(at)}</span>}
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
  const resolve = useSupportMutation((v: Resolution) => supportApi.resolve(m.id, v), t("saved"));
  const done = m.status === "answered" || m.status === "closed";
  const botSaid = m.answer_text && m.stage !== "panel";
  const send = () => answer.mutate(undefined, { onSuccess: () => setText("") });

  return (
    <>
      <div className="flex items-center gap-2 border-b px-3 py-2.5 sm:px-4">
        <Button size="icon" variant="ghost" className="lg:hidden" onClick={onBack} aria-label={t("back")}><ArrowLeft className="size-4" /></Button>
        <Initials name={m.user_name} className="size-8 2xl:hidden" />
        <div className="min-w-0 flex-1">
          <div className="truncate text-sm font-medium">{m.user_name}{m.user_username && <span className="font-normal text-muted-foreground"> · @{m.user_username}</span>}</div>
          <div className="truncate text-xs text-muted-foreground">{m.group_title}</div>
        </div>
        {m.feedback === 1 && <ThumbsUp className="size-4 text-success" />}
        {m.feedback === -1 && <ThumbsDown className="size-4 text-destructive" />}
        <MsgBadge status={m.status} t={t} />
        {m.link && (
          <Button size="icon" variant="ghost" className="2xl:hidden" asChild>
            <a href={m.link} target="_blank" rel="noreferrer" title={t("openInTelegram")} aria-label={t("openInTelegram")}><ExternalLink className="size-4" /></a>
          </Button>
        )}
        {!done && <Button size="sm" variant="ghost" disabled={close.isPending} onClick={() => close.mutate(undefined)}><X className="size-4" /><span className="hidden sm:inline">{t("closeQ")}</span></Button>}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-b bg-muted/30 px-3 py-2 text-xs sm:px-4">
        <span className="min-w-0 flex-1 basis-60">
          <span className="font-medium text-muted-foreground">{t("dProblem")}:</span> <span className="break-words">{m.problem || m.text || m.ocr_text.slice(0, 120) || t("photo")}</span>
        </span>
        <ResolutionMark r={m.resolution} t={t} label />
        <span className="flex shrink-0 gap-1">
          <Button size="sm" variant={m.resolution === "yes" ? "default" : "outline"} className="h-7 px-2 text-xs" disabled={resolve.isPending}
            onClick={() => resolve.mutate(m.resolution === "yes" ? "" : "yes")} title={m.resolution === "yes" ? t("markClear") : t("markYes")}>
            <CircleCheck className="size-3.5" />{t("markYes")}
          </Button>
          <Button size="sm" variant={m.resolution === "no" ? "destructive" : "outline"} className="h-7 px-2 text-xs" disabled={resolve.isPending}
            onClick={() => resolve.mutate(m.resolution === "no" ? "" : "no")} title={m.resolution === "no" ? t("markClear") : t("markNo")}>
            <CircleX className="size-3.5" />{t("markNo")}
          </Button>
        </span>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto bg-[radial-gradient(circle_at_1px_1px,var(--color-border)_1px,transparent_0)] bg-[length:18px_18px] p-4">
        <Bubble side="left" who={m.user_name || "—"} at={m.created_at}>
          {m.text && <p className="whitespace-pre-wrap">{m.text}</p>}
          <MediaRow items={m.media} />
          {m.ocr_text && <details className="mt-1 text-xs text-muted-foreground"><summary className="cursor-pointer">{t("ocr")}</summary><p className="mt-1 whitespace-pre-wrap">{m.ocr_text}</p></details>}
        </Bubble>
        {m.staff_answers.map((a, i) => (
          <Bubble key={i} side={a.kind === "info" || a.kind === "feedback" ? "left" : "right"}
            tone={a.kind === "feedback" ? "info" : a.kind}
            who={`${a.by} · ${t(`k_${a.kind}` as SKey)}`} at={a.at}>
            <p className="whitespace-pre-wrap">{a.text}</p>
            <MediaRow items={a.media} />
          </Bubble>
        ))}
        {botSaid && (
          <Bubble side="right" tone="bot" icon={<Sparkles className="size-3 text-primary" />}
            who={`${m.status === "answered" && m.answered_by === "bot" ? t("botAnswered") : t("botDraft")}${m.stage ? ` · ${stageLabel(m.stage, t)}` : ""}${m.confidence ? ` · ${m.confidence}%` : ""}`}>
            <p className="whitespace-pre-wrap">{m.answer_text}</p>
            {m.entry_title && (
              <Link className="mt-1.5 inline-flex items-center gap-1 text-xs text-primary hover:underline" href={`/support/knowledge?entry=${m.entry}`}>
                <BookOpen className="size-3" />{m.entry_title}
              </Link>
            )}
            {!done && <div className="mt-2"><Button size="sm" variant="outline" className="bg-background" onClick={() => setText(m.answer_text)}>{t("useDraft")}</Button></div>}
          </Bubble>
        )}
        {m.stage === "panel" && m.answer_text && (
          <Bubble side="right" tone="staff" who={`${m.answered_by} · ${t("s_panel")}`} at={m.answered_at ?? undefined}>
            <p className="whitespace-pre-wrap">{m.answer_text}</p>
          </Bubble>
        )}
      </div>

      {!done ? (
        <div className="border-t bg-card p-3">
          <div className="rounded-xl border bg-background focus-within:ring-2 focus-within:ring-ring/40">
            <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} placeholder={t("answerPlaceholder")}
              className="resize-none border-0 bg-transparent shadow-none focus-visible:ring-0"
              onKeyDown={(e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey) && text.trim().length > 1) send(); }} />
            <div className="flex flex-wrap items-center gap-x-4 gap-y-2 border-t px-3 py-2">
              <label className="flex items-center gap-2 text-xs"><Switch checked={save} onCheckedChange={setSave} />{t("saveToKb")}</label>
              {can.edit && save && <label className="flex items-center gap-2 text-xs"><Switch checked={approve} onCheckedChange={setApprove} />{t("approveNow")}</label>}
              <span className="ml-auto hidden text-[11px] text-muted-foreground sm:inline">Ctrl + Enter</span>
              <Button size="sm" disabled={text.trim().length < 2 || answer.isPending} onClick={send}>
                <Send className="size-4" />{t("send")}
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-2 border-t p-3 text-xs text-muted-foreground"><CheckCheck className="size-4 text-success" />{t("threadDone")}</div>
      )}
    </>
  );
}
