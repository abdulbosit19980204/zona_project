"use client";

import { useQuery } from "@tanstack/react-query";
import { Bot, CheckCheck, Image as ImageIcon, Inbox, MessageSquareReply, Send, ThumbsDown, ThumbsUp, UserRound, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { EmptyState, Page, PageHeader, StatCard } from "@/components/common/page";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { useCan } from "@/hooks/use-org";

import { supportApi, type MsgStatus, type SupportMessage } from "./api";
import { fmtDate, MsgBadge, stageLabel, useSupportMutation } from "./common";
import { useSt, type ST } from "./i18n";

const TABS: (MsgStatus | "open" | "all")[] = ["open", "escalated", "drafted", "answered", "closed", "all"];

/** Guruh savollari: statistika, botlar holati, savollar ro'yxati va paneldan javob berish. */
export function SupportInbox() {
  const t = useSt();
  const [tab, setTab] = useState<(typeof TABS)[number]>("open");
  const [q, setQ] = useState("");
  const status = tab === "open" ? "escalated,drafted,new" : tab;
  const stats = useQuery({ queryKey: ["support", "stats"], queryFn: () => supportApi.stats(7), refetchInterval: 30_000 });
  const list = useQuery({
    queryKey: ["support", "messages", status, q],
    queryFn: () => supportApi.messages({ status, ...(q ? { q } : {}), limit: 200 }),
    refetchInterval: 20_000,
  });
  const s = stats.data;
  const botClosed = (s?.by_stage.template ?? 0) + (s?.by_stage.faq ?? 0) + (s?.by_stage.rule ?? 0) + (s?.by_stage.ai ?? 0);
  const queue = (s?.entries.new ?? 0) + (s?.entries.review ?? 0) + (s?.pending_edits ?? 0);

  return (
    <Page>
      <PageHeader title={t("inboxTitle")} description={t("inboxDesc")} />
      <div className="mb-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard label={t("kpiTotal")} value={s?.total ?? "—"} icon={Inbox} />
        <StatCard label={t("kpiBot")} value={botClosed} icon={Bot} tone="success" />
        <StatCard label={t("kpiHuman")} value={s?.by_status.escalated ?? 0} icon={UserRound} tone="warning" />
        <Link href="/support/review"><StatCard label={t("kpiQueue")} value={queue} icon={CheckCheck} /></Link>
      </div>

      {s && s.bots.length > 0 && (
        <Card className="mb-4 gap-2 p-3">
          <div className="text-sm font-medium">{t("botsState")}</div>
          {s.bots.map((b) => (
            <div key={b.id} className="flex flex-wrap items-center gap-2 text-sm">
              <span className={`size-2 rounded-full ${b.enabled && !b.last_error ? "bg-success" : "bg-warning"}`} />
              <span className="font-medium">{b.name}</span>
              {b.username && <span className="text-muted-foreground">@{b.username}</span>}
              <Badge variant="outline" className="font-normal">{t(`mode_${b.mode}`)}</Badge>
              <span className="text-xs text-muted-foreground">{b.last_error || (b.last_ok_at ? `${t("botOk")} · ${fmtDate(b.last_ok_at)}` : "")}</span>
              {!b.admin_chat && <span className="text-xs text-warning">{t("botNoAdmin")}</span>}
            </div>
          ))}
        </Card>
      )}

      <div className="mb-3 flex flex-wrap items-center gap-3">
        <Tabs value={tab} onValueChange={(v) => setTab(v as typeof tab)}>
          <TabsList>
            {TABS.map((k) => (
              <TabsTrigger key={k} value={k}>{k === "open" ? t("needsAnswer") : k === "all" ? t("all") : t(`m_${k}`)}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("search")} className="h-9 max-w-64" />
      </div>

      {list.isLoading && <div className="grid gap-2">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28" />)}</div>}
      {list.data && list.data.length === 0 && (
        <EmptyState icon={Inbox} title={t("empty")} hint={s && s.bots.length === 0 ? t("noGroupsYet") : undefined} />
      )}
      <div className="grid gap-3">
        {list.data?.map((m) => <MessageCard key={m.id} m={m} t={t} />)}
      </div>
    </Page>
  );
}

function MessageCard({ m, t }: { m: SupportMessage; t: ST }) {
  const can = useCan();
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [save, setSave] = useState(true);
  const [approve, setApprove] = useState(false);
  const answer = useSupportMutation(() => supportApi.answer(m.id, text, save, approve), t("sent"));
  const close = useSupportMutation(() => supportApi.close(m.id));
  const done = m.status === "answered" || m.status === "closed";

  return (
    <Card className="gap-2 p-4">
      <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
        <MsgBadge status={m.status} t={t} />
        <span className="font-medium text-foreground">{m.group_title}</span>
        <span>· {m.user_name}{m.user_username && ` (@${m.user_username})`}</span>
        <span>· {fmtDate(m.created_at)}</span>
        {m.feedback === 1 && <ThumbsUp className="size-3.5 text-success" />}
        {m.feedback === -1 && <ThumbsDown className="size-3.5 text-destructive" />}
      </div>
      {m.text && <p className="whitespace-pre-wrap text-sm">{m.text}</p>}
      {m.has_photo && (
        <div className="rounded-lg border bg-muted/40 p-2 text-xs">
          <div className="mb-1 flex items-center gap-1 font-medium"><ImageIcon className="size-3.5" />{m.ocr_text ? t("ocr") : t("photo")}</div>
          {m.ocr_text && <p className="line-clamp-6 whitespace-pre-wrap text-muted-foreground">{m.ocr_text}</p>}
        </div>
      )}
      {m.answer_text && (
        <div className="rounded-lg border-l-2 border-primary/60 bg-primary/5 p-2 text-sm">
          <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <Bot className="size-3.5" />{m.stage === "panel" ? t("answeredBy") : t("botDraft")}
            {m.stage && <Badge variant="outline" className="h-5 font-normal">{stageLabel(m.stage, t)}</Badge>}
            {m.confidence > 0 && <span>{m.confidence}% {t("confidence")}</span>}
            {m.entry_title && <Link className="text-primary hover:underline" href={`/support/knowledge?entry=${m.entry}`}>{m.entry_title}</Link>}
            {m.answered_by && <span>· {m.answered_by}</span>}
          </div>
          <p className="whitespace-pre-wrap">{m.answer_text}</p>
        </div>
      )}
      {m.staff_answers.map((a, i) => (
        <div key={i} className={`rounded-lg border-l-2 p-2 text-sm ${a.kind === "staff" ? "border-success/60 bg-success/5"
          : a.kind === "clarify" ? "border-warning/60 bg-warning/5" : "border-muted-foreground/40 bg-muted/40"}`}>
          <div className="mb-1 flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
            <MessageSquareReply className="size-3.5" />
            <Badge variant="outline" className="h-5 font-normal">{t(`k_${a.kind}`)}</Badge>{a.by} · {fmtDate(a.at)}
          </div>
          <p className="whitespace-pre-wrap">{a.text}</p>
          {a.ocr && <p className="mt-1 line-clamp-3 text-xs text-muted-foreground">🖼 {a.ocr}</p>}
        </div>
      ))}

      {!done && (
        <div className="flex flex-wrap gap-2">
          <Button size="sm" variant={open ? "secondary" : "default"} onClick={() => setOpen(!open)}>
            <MessageSquareReply className="size-4" />{t("writeAnswer")}
          </Button>
          <Button size="sm" variant="ghost" disabled={close.isPending} onClick={() => close.mutate(undefined)}>
            <X className="size-4" />{t("closeQ")}
          </Button>
        </div>
      )}
      {open && !done && (
        <div className="grid gap-2 rounded-lg border p-3">
          {m.answer_text && !text && (
            <Button size="sm" variant="outline" className="justify-self-start" onClick={() => setText(m.answer_text)}>{t("useDraft")}</Button>
          )}
          <Textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} placeholder={t("answerPlaceholder")} />
          <label className="flex items-center gap-2 text-sm"><Checkbox checked={save} onCheckedChange={(v) => setSave(!!v)} />{t("saveToKb")}</label>
          {can.edit && save && (
            <label className="flex items-center gap-2 text-sm"><Checkbox checked={approve} onCheckedChange={(v) => setApprove(!!v)} />{t("approveNow")}</label>
          )}
          <Button size="sm" className="justify-self-start" disabled={text.trim().length < 2 || answer.isPending}
            onClick={() => answer.mutate(undefined, { onSuccess: () => { setOpen(false); setText(""); } })}>
            <Send className="size-4" />{t("send")}
          </Button>
        </div>
      )}
    </Card>
  );
}
