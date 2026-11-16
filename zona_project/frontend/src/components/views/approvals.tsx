"use client";

import { format } from "date-fns";
import { ArrowRight, Bot, Check, CheckCheck, Clock, GitPullRequestArrow, Inbox, Lightbulb, Undo2, User, X } from "lucide-react";
import { useLocale, useTranslations } from "next-intl";
import { useMemo, useState } from "react";

import { DATE_LOCALES } from "@/components/common/activity";
import { EmptyState, Page, PageHeader } from "@/components/common/page";
import { ProposeDialog } from "@/components/forms/propose-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { Switch } from "@/components/ui/switch";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useApprovals, useCan, useMe, useModel, useOrgMutation } from "@/hooks/use-org";
import { approvalsApi } from "@/lib/api/endpoints";
import type { ChangeRequest, ChangeSource, ChangeStatus } from "@/lib/api/types";
import { cn } from "@/lib/utils";

const STATUS_TONE: Record<ChangeStatus, string> = {
  pending: "border-warning/50 text-warning",
  approved: "border-success/50 text-success",
  rejected: "border-destructive/50 text-destructive",
  cancelled: "text-muted-foreground",
};
const SOURCE_ICON = { user: User, rule: Lightbulb, ai: Bot } as const;
const SOURCE_TONE: Record<ChangeSource, string> = {
  user: "text-muted-foreground",
  rule: "border-warning/50 text-warning",
  ai: "border-primary/50 bg-primary/10 text-primary",
};

/**
 * Tasdiqlash oqimi: xodim, qoida yoki AI mas'uliyatni almashtirishni taklif qiladi; muharrir/admin
 * bittalab, tanlab yoki hammasini birdan qabul qiladi yoki rad etadi. Qabul qilingan o'zgarish darhol qo'llanadi.
 */
export function Approvals() {
  const t = useTranslations();
  const can = useCan();
  const [status, setStatus] = useState<ChangeStatus | "all">("pending");
  const [source, setSource] = useState<ChangeSource | "all">("all");
  const [mine, setMine] = useState(!can.edit);
  const [propose, setPropose] = useState(false);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [note, setNote] = useState("");
  const { data, isLoading } = useApprovals(status, mine);

  const list = useMemo(() => (data ?? []).filter((r) => source === "all" || r.source === source), [data, source]);
  const pendingIds = list.filter((r) => r.status === "pending").map((r) => r.id);
  const chosen = pendingIds.filter((id) => selected.has(id));
  const counts = useMemo(() => {
    const c = { all: data?.length ?? 0, user: 0, rule: 0, ai: 0 };
    for (const r of data ?? []) c[r.source] += 1;
    return c;
  }, [data]);
  const savedHours = list.filter((r) => chosen.includes(r.id)).reduce((s, r) => s + (r.hours ?? 0), 0);

  const bulk = useOrgMutation(
    ({ ids, action }: { ids: number[]; action: "approve" | "reject" }) => approvalsApi.bulk(ids, action, note),
    (r) => t("approvals.bulkDone", { done: r.done, failed: r.results.length - r.done }),
  );
  const run = (ids: number[], action: "approve" | "reject") =>
    bulk.mutate({ ids, action }, { onSuccess: () => { setSelected(new Set()); setNote(""); } });
  const toggle = (id: number) => setSelected((s) => {
    const next = new Set(s);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
  const allChosen = pendingIds.length > 0 && chosen.length === pendingIds.length;

  return (
    <Page>
      <PageHeader
        title={t("nav.approvals")}
        description={can.edit ? t("approvals.descriptionEdit") : t("approvals.descriptionView")}
        actions={<Button onClick={() => setPropose(true)}><GitPullRequestArrow className="size-4" />{t("approvals.propose")}</Button>}
      />
      <div className="mb-3 flex flex-wrap items-center gap-4">
        <Tabs value={status} onValueChange={(v) => { setStatus(v as ChangeStatus | "all"); setSelected(new Set()); }}>
          <TabsList>
            {(["pending", "approved", "rejected", "cancelled", "all"] as const).map((s) => (
              <TabsTrigger key={s} value={s}>{t(`approvals.status.${s}`)}</TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        <label className="flex items-center gap-2 text-sm text-muted-foreground">
          <Switch checked={mine} onCheckedChange={setMine} />{t("approvals.mine")}
        </label>
      </div>
      <div className="mb-4 flex flex-wrap gap-1.5">
        {(["all", "ai", "rule", "user"] as const).map((s) => {
          const Icon = s === "all" ? Inbox : SOURCE_ICON[s];
          return (
            <Button key={s} size="sm" variant={source === s ? "default" : "outline"} onClick={() => { setSource(s); setSelected(new Set()); }}>
              <Icon className="size-3.5" />{t(`approvals.source.${s}`)} · {counts[s]}
            </Button>
          );
        })}
      </div>

      {/* tanlab yoki hammasini birdan qabul qilish / rad etish */}
      {can.edit && pendingIds.length > 0 && (
        <Card className="sticky top-0 z-10 mb-3 flex-row flex-wrap items-center gap-2 p-3 shadow-sm">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox checked={allChosen ? true : chosen.length ? "indeterminate" : false}
              onCheckedChange={() => setSelected(allChosen ? new Set() : new Set(pendingIds))} />
            {chosen.length ? t("approvals.selected", { count: chosen.length }) : t("approvals.selectAll", { count: pendingIds.length })}
          </label>
          {savedHours > 0 && <span className="flex items-center gap-1 font-mono text-xs text-success"><Clock className="size-3" />−{Math.round(savedHours * 10) / 10} {t("time.hPerWeek")}</span>}
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("approvals.notePlaceholder")} className="h-8 min-w-48 flex-1" />
          <Button size="sm" disabled={!chosen.length || bulk.isPending} onClick={() => run(chosen, "approve")}>
            <Check className="size-4" />{t("approvals.approveSelected")}
          </Button>
          <Button size="sm" variant="outline" disabled={!chosen.length || bulk.isPending} onClick={() => run(chosen, "reject")}>
            <X className="size-4" />{t("approvals.rejectSelected")}
          </Button>
          <Button size="sm" variant="ghost" disabled={bulk.isPending} onClick={() => run(pendingIds, "approve")}>
            <CheckCheck className="size-4" />{t("approvals.approveAll", { count: pendingIds.length })}
          </Button>
        </Card>
      )}

      {isLoading && <div className="grid gap-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}</div>}
      {data && !list.length && <EmptyState icon={Inbox} title={t("approvals.empty")} hint={t("approvals.emptyHint")} />}
      <div className="grid gap-3">
        {list.map((r) => (
          <RequestCard key={r.id} request={r} checked={selected.has(r.id)} onCheck={can.edit && r.status === "pending" ? () => toggle(r.id) : undefined} />
        ))}
      </div>
      <ProposeDialog open={propose} onOpenChange={setPropose} />
    </Page>
  );
}

function RequestCard({ request: r, checked, onCheck }: { request: ChangeRequest; checked: boolean; onCheck?: () => void }) {
  const t = useTranslations();
  const locale = useLocale() as keyof typeof DATE_LOCALES;
  const can = useCan();
  const me = useMe();
  const model = useModel();
  const [note, setNote] = useState("");
  const approve = useOrgMutation(() => approvalsApi.approve(r.id, note), t("approvals.approved"));
  const reject = useOrgMutation(() => approvalsApi.reject(r.id, note), t("approvals.rejected"));
  const cancel = useOrgMutation(() => approvalsApi.cancel(r.id), t("approvals.cancelled"));
  const busy = approve.isPending || reject.isPending || cancel.isPending;
  const fmt = (d: string) => format(new Date(d), "d MMM yyyy, HH:mm", { locale: DATE_LOCALES[locale] });
  const SourceIcon = SOURCE_ICON[r.source] ?? User;

  // mas'ulni almashtirish: savol va xodimlar tanlangan tilda (model orqali), bo'lmasa — saqlangan sarlavha
  const p = r.payload as { task?: number; owner?: number | null };
  const task = r.kind === "task_owner" && p.task ? model.task.get(p.task) : undefined;
  const from = task?.owner ? model.member.get(task.owner) : undefined;
  const to = p.owner ? model.member.get(p.owner) : undefined;

  return (
    <Card className={cn("gap-3 p-4", r.status === "pending" && "border-l-2 border-l-warning", checked && "ring-2 ring-primary/50")}>
      <div className="flex flex-wrap items-start gap-3">
        {onCheck && <Checkbox checked={checked} onCheckedChange={onCheck} className="mt-1" aria-label={t("approvals.select")} />}
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="outline" className={SOURCE_TONE[r.source]}><SourceIcon className="size-3" />{t(`approvals.source.${r.source}`)}</Badge>
            <Badge variant="outline">{t(`approvals.kinds.${r.kind}`)}</Badge>
            <Badge variant="outline" className={STATUS_TONE[r.status]}>{t(`approvals.status.${r.status}`)}</Badge>
            {r.hours ? <span className="flex items-center gap-1 font-mono text-xs text-success"><Clock className="size-3" />−{r.hours} {t("time.hPerWeek")}</span> : null}
            <span className="text-xs text-muted-foreground">#{r.id}</span>
          </div>
          {task ? (
            <div className="mt-2">
              <div className="font-medium">{task.title}</div>
              <div className="mt-1 flex flex-wrap items-center gap-1.5 text-xs">
                {r.status === "pending" && <span className="rounded-full border px-2 py-0.5 text-muted-foreground">{from?.name ?? t("common.unassigned")}</span>}
                {r.status === "pending" && <ArrowRight className="size-3 text-muted-foreground" />}
                <span className="rounded-full border border-primary/40 bg-primary/10 px-2 py-0.5 text-primary">{to?.name ?? t("common.unassigned")}</span>
              </div>
            </div>
          ) : (
            <div className="mt-2 font-medium">{r.title}</div>
          )}
          {r.reason && <p className="mt-1.5 text-sm text-muted-foreground">“{r.reason}”</p>}
          <div className="mt-2 text-xs text-muted-foreground">
            {t("approvals.by", { name: r.requested_by_name || "—" })} · {fmt(r.created_at)}
            {r.decided_at && <> · {t("approvals.decidedBy", { name: r.decided_by_name || "—" })} · {fmt(r.decided_at)}</>}
          </div>
          {r.decision_note && <p className="mt-1 text-xs">{t("approvals.note")}: {r.decision_note}</p>}
        </div>
        {r.status === "pending" && me && r.requested_by === me.id && (
          <Button size="sm" variant="ghost" disabled={busy} onClick={() => cancel.mutate(undefined)}><Undo2 className="size-4" />{t("approvals.cancel")}</Button>
        )}
      </div>
      {r.status === "pending" && can.edit && (
        <div className="flex flex-wrap items-center gap-2 border-t pt-3">
          <Input value={note} onChange={(e) => setNote(e.target.value)} placeholder={t("approvals.notePlaceholder")} className="h-8 min-w-60 flex-1" />
          <Button size="sm" disabled={busy} onClick={() => approve.mutate(undefined)}><Check className="size-4" />{t("approvals.approve")}</Button>
          <Button size="sm" variant="outline" disabled={busy} onClick={() => reject.mutate(undefined)}><X className="size-4" />{t("approvals.reject")}</Button>
        </div>
      )}
    </Card>
  );
}
